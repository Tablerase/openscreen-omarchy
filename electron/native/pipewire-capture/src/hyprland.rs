//! Hyprland cursor sampler for environments where the ScreenCast portal does
//! not advertise METADATA cursor mode (xdg-desktop-portal-hyprland advertises
//! AvailableCursorModes = 3: Hidden | Embedded).
//!
//! Hyprland exposes its cursor position and monitor layout over its UNIX socket:
//! `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock`
//!
//! By querying `j/cursorpos` and `j/monitors`, we can map the compositor-wide
//! cursor coordinates into stream pixel coordinates for the recorded output.

use std::io::{Read, Write};
use std::os::unix::fs::MetadataExt;
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use crate::shim::{CursorEvent, StreamEvent};
use crate::Message;

/// Returns true if running under a live Hyprland session.
pub fn is_active() -> bool {
    std::env::var_os("HYPRLAND_INSTANCE_SIGNATURE").is_some()
}

fn socket_path() -> Option<PathBuf> {
    let sig = std::env::var("HYPRLAND_INSTANCE_SIGNATURE").ok()?;
    let runtime_dir = std::env::var("XDG_RUNTIME_DIR").unwrap_or_else(|_| {
        let uid = std::fs::metadata("/proc/self")
            .map(|m| m.uid())
            .unwrap_or(1000);
        format!("/run/user/{uid}")
    });
    Some(
        PathBuf::from(runtime_dir)
            .join("hypr")
            .join(sig)
            .join(".socket.sock"),
    )
}

fn query_socket(command: &[u8]) -> Option<String> {
    let path = socket_path()?;
    let mut stream = UnixStream::connect(path).ok()?;
    stream.write_all(command).ok()?;
    let mut buf = Vec::new();
    stream.read_to_end(&mut buf).ok()?;
    String::from_utf8(buf).ok()
}

use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct MonitorInfo {
    #[allow(dead_code)]
    pub name: String,
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
    pub scale: f64,
    #[serde(default)]
    pub focused: bool,
}

pub fn get_monitors() -> Vec<MonitorInfo> {
    let Some(raw) = query_socket(b"j/monitors") else {
        return Vec::new();
    };
    serde_json::from_str::<Vec<MonitorInfo>>(&raw).unwrap_or_default()
}

#[derive(Deserialize)]
struct CursorPos {
    x: f64,
    y: f64,
}

pub fn get_cursor_pos() -> Option<(f64, f64)> {
    let raw = query_socket(b"j/cursorpos")?;
    let pos = serde_json::from_str::<CursorPos>(&raw).ok()?;
    Some((pos.x, pos.y))
}

fn to_stream_position(
    cursor: (f64, f64),
    monitor: &MonitorInfo,
    stream_origin: Option<(i32, i32)>,
) -> (i32, i32) {
    // Some portal backends report (0, 0) for every monitor. Trust a stream
    // origin only when it falls on the monitor selected for this stream.
    let (origin_x, origin_y) = stream_origin
        .filter(|(x, y)| monitor_contains(monitor, *x as f64, *y as f64))
        .map(|(x, y)| (x as f64, y as f64))
        .unwrap_or((monitor.x as f64, monitor.y as f64));
    (
        ((cursor.0 - origin_x) * monitor.scale).round() as i32,
        ((cursor.1 - origin_y) * monitor.scale).round() as i32,
    )
}

fn monitor_contains(monitor: &MonitorInfo, x: f64, y: f64) -> bool {
    let logical_w = monitor.width as f64 / monitor.scale;
    let logical_h = monitor.height as f64 / monitor.scale;
    x >= monitor.x as f64
        && x < monitor.x as f64 + logical_w
        && y >= monitor.y as f64
        && y < monitor.y as f64 + logical_h
}

fn matching_monitor_for_size<'a>(
    monitors: &'a [MonitorInfo],
    size: (i32, i32),
    cursor: (f64, f64),
) -> Option<&'a MonitorInfo> {
    let matching: Vec<_> = monitors
        .iter()
        .filter(|monitor| monitor.width == size.0 && monitor.height == size.1)
        .collect();
    match matching.as_slice() {
        [monitor] => Some(*monitor),
        [] => None,
        _ => matching
            .iter()
            .copied()
            .find(|monitor| monitor_contains(monitor, cursor.0, cursor.1))
            .or_else(|| matching.iter().copied().find(|monitor| monitor.focused)),
    }
}

fn target_monitor<'a>(
    monitors: &'a [MonitorInfo],
    stream_origin: Option<(i32, i32)>,
    stream_size: Option<(i32, i32)>,
    cursor: (f64, f64),
) -> Option<&'a MonitorInfo> {
    // A uniquely matching negotiated stream size identifies full-monitor
    // captures more reliably than the portal origin. Some portal backends
    // report (0, 0) for every stream, which can accidentally point at a real
    // monitor at the top-left of a multi-monitor layout.
    let unique_monitor_by_size = stream_size.and_then(|size| {
        let mut matching = monitors
            .iter()
            .filter(|monitor| monitor.width == size.0 && monitor.height == size.1);
        let first = matching.next()?;
        matching.next().is_none().then_some(first)
    });
    let monitor_at_origin = stream_origin.and_then(|(x, y)| {
        monitors.iter().find(|monitor| {
            (monitor.x == x && monitor.y == y) || monitor_contains(monitor, x as f64, y as f64)
        })
    });
    let monitor_by_size =
        stream_size.and_then(|size| matching_monitor_for_size(monitors, size, cursor));

    unique_monitor_by_size
        .or(monitor_at_origin)
        .or(monitor_by_size)
        .or_else(|| {
            monitors
                .iter()
                .find(|monitor| monitor_contains(monitor, cursor.0, cursor.1))
        })
        .or_else(|| monitors.iter().find(|monitor| monitor.focused))
        .or_else(|| monitors.first())
}

pub struct HyprlandSampler {
    running: Arc<AtomicBool>,
}

impl HyprlandSampler {
    pub fn spawn(
        sender: Sender<Message>,
        interval: Duration,
        stream_position: Arc<Mutex<Option<(i32, i32)>>>,
        stream_size: Arc<Mutex<Option<(i32, i32)>>>,
    ) -> Self {
        let running = Arc::new(AtomicBool::new(true));
        let thread_running = Arc::clone(&running);
        let debug = std::env::var("OPENSCREEN_PIPEWIRE_DEBUG")
            .map(|value| !matches!(value.as_str(), "" | "0" | "false"))
            .unwrap_or(false);

        thread::spawn(move || {
            let mut monitors = get_monitors();
            let mut last_monitors_fetch = std::time::Instant::now();
            let mut logged_mapping = false;

            while thread_running.load(Ordering::Relaxed) {
                thread::sleep(interval);

                // Refresh monitors every 5 seconds in case of display reconfiguration
                if last_monitors_fetch.elapsed() > Duration::from_secs(5) {
                    monitors = get_monitors();
                    last_monitors_fetch = std::time::Instant::now();
                }

                let Some((cx, cy)) = get_cursor_pos() else {
                    continue;
                };

                let pos = *stream_position.lock().unwrap();
                let size = *stream_size.lock().unwrap();

                // Prefer a portal origin that belongs to a monitor. Some
                // backends report (0, 0) even when the chosen monitor is
                // elsewhere in Hyprland's global layout, so try the stream
                // dimensions before falling back to the focused output.
                let target_monitor = target_monitor(&monitors, pos, size, (cx, cy));

                let (stream_x, stream_y) = if let Some(m) = target_monitor {
                    // Portal position is the region's logical origin. For a
                    // full monitor it equals m.x/m.y; for a selected region it
                    // is inside the monitor and must be subtracted before
                    // scaling into the region's pixel coordinates.
                    to_stream_position((cx, cy), m, pos)
                } else if let Some((px, py)) = pos {
                    // Fallback using portal position if monitor list is empty
                    (
                        (cx - px as f64).round() as i32,
                        (cy - py as f64).round() as i32,
                    )
                } else {
                    (cx.round() as i32, cy.round() as i32)
                };

                if debug && !logged_mapping && (pos.is_some() || size.is_some()) {
                    eprintln!(
                        "[hyprland-cursor] raw=({cx:.2},{cy:.2}) stream_origin={pos:?} \
                         stream_size={size:?} monitor={target_monitor:?} \
                         mapped=({stream_x},{stream_y})"
                    );
                    logged_mapping = true;
                }

                let _ = sender.send(Message::Stream(StreamEvent::Cursor(CursorEvent {
                    x: stream_x,
                    y: stream_y,
                    hotspot_x: 0,
                    hotspot_y: 0,
                    id: 0,
                    bitmap: None,
                })));
            }
        });

        Self { running }
    }
}

impl Drop for HyprlandSampler {
    fn drop(&mut self) {
        self.running.store(false, Ordering::Relaxed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn socket_path_construction() {
        if let Ok(sig) = std::env::var("HYPRLAND_INSTANCE_SIGNATURE") {
            let path = socket_path().expect("socket path exists under Hyprland");
            assert!(path.to_string_lossy().contains(&sig));
            assert!(path.ends_with(".socket.sock"));
        }
    }

    #[test]
    fn queries_cursor_and_monitors_live_if_active() {
        if !is_active() {
            return;
        }
        let pos = get_cursor_pos();
        assert!(
            pos.is_some(),
            "cursor position should be queried successfully"
        );
        let monitors = get_monitors();
        assert!(!monitors.is_empty(), "monitors list should not be empty");
    }

    #[test]
    fn coordinate_scaling() {
        let m = MonitorInfo {
            name: "eDP-1".to_string(),
            x: 575,
            y: 0,
            width: 2256,
            height: 1504,
            scale: 1.6,
            focused: true,
        };
        let cx = 1078.0;
        let cy = 551.0;
        let (sx, sy) = to_stream_position((cx, cy), &m, None);
        assert_eq!(sx, 805);
        assert_eq!(sy, 882);
    }

    #[test]
    fn region_origin_is_subtracted_before_scaling() {
        let monitor = MonitorInfo {
            name: "eDP-1".to_string(),
            x: 575,
            y: 0,
            width: 2256,
            height: 1504,
            scale: 1.6,
            focused: true,
        };

        // A selected region begins at logical (700, 100); the pointer at
        // (750, 150) must be 80x80 px into its 1.6x scaled stream.
        assert_eq!(
            to_stream_position((750.0, 150.0), &monitor, Some((700, 100))),
            (80, 80)
        );
    }

    #[test]
    fn unmatched_portal_origin_falls_back_to_unique_stream_size() {
        let monitors = vec![
            MonitorInfo {
                name: "DP-3".to_string(),
                x: 0,
                y: -1440,
                width: 2560,
                height: 1440,
                scale: 1.0,
                focused: true,
            },
            MonitorInfo {
                name: "eDP-1".to_string(),
                x: 575,
                y: 0,
                width: 2256,
                height: 1504,
                scale: 1.6,
                focused: false,
            },
        ];

        // This mirrors the observed session: the portal reports (0, 0) for
        // the 2256x1504 eDP stream, although Hyprland places that monitor at
        // (575, 0). A bogus origin must not force the scale-1 DP-3 fallback.
        let target = target_monitor(&monitors, Some((0, 0)), Some((2256, 1504)), (726.0, 207.0))
            .expect("unique stream-size match after unmatched origin");
        assert_eq!(target.name, "eDP-1");
        assert_eq!(
            to_stream_position((726.0, 207.0), target, Some((0, 0))),
            (242, 331)
        );
    }

    #[test]
    fn unique_stream_size_beats_bogus_origin_on_another_monitor() {
        let monitors = vec![
            MonitorInfo {
                name: "DP-1".to_string(),
                x: 0,
                y: 0,
                width: 1920,
                height: 1080,
                scale: 1.0,
                focused: true,
            },
            MonitorInfo {
                name: "DP-2".to_string(),
                x: 1920,
                y: 0,
                width: 2560,
                height: 1440,
                scale: 1.25,
                focused: false,
            },
        ];

        // A portal reporting (0, 0) must not make a capture of DP-2 inherit
        // DP-1's origin and scale just because DP-1 occupies the top-left.
        let target = target_monitor(&monitors, Some((0, 0)), Some((2560, 1440)), (2200.0, 200.0))
            .expect("unique stream-size match");
        assert_eq!(target.name, "DP-2");
        assert_eq!(
            to_stream_position((2200.0, 200.0), target, Some((0, 0))),
            (350, 250)
        );
    }

    #[test]
    fn negative_monitor_origins_and_fractional_scales_map_to_stream_pixels() {
        let monitor = MonitorInfo {
            name: "DP-3".to_string(),
            x: -1600,
            y: -180,
            width: 2560,
            height: 1440,
            scale: 1.25,
            focused: true,
        };

        assert_eq!(
            to_stream_position((-1520.0, -100.0), &monitor, None),
            (100, 100)
        );
    }
}
