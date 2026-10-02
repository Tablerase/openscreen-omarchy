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

        thread::spawn(move || {
            let mut monitors = get_monitors();
            let mut last_monitors_fetch = std::time::Instant::now();

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

                // Find matching monitor by portal position or stream size
                let target_monitor = if let Some((px, py)) = pos {
                    monitors.iter().find(|m| m.x == px && m.y == py)
                } else if let Some((sw, sh)) = size {
                    let matching: Vec<_> = monitors
                        .iter()
                        .filter(|m| m.width == sw && m.height == sh)
                        .collect();
                    if matching.len() == 1 {
                        Some(matching[0])
                    } else if matching.len() > 1 {
                        // If multiple monitors share the same resolution, pick the one the cursor is inside
                        matching
                            .into_iter()
                            .find(|m| {
                                let logical_w = m.width as f64 / m.scale;
                                let logical_h = m.height as f64 / m.scale;
                                cx >= m.x as f64
                                    && cx < m.x as f64 + logical_w
                                    && cy >= m.y as f64
                                    && cy < m.y as f64 + logical_h
                            })
                            .or_else(|| monitors.iter().find(|m| m.focused))
                    } else {
                        monitors
                            .iter()
                            .find(|m| m.focused)
                            .or_else(|| monitors.first())
                    }
                } else {
                    monitors
                        .iter()
                        .find(|m| m.focused)
                        .or_else(|| monitors.first())
                };

                let (stream_x, stream_y) = if let Some(m) = target_monitor {
                    let sx = ((cx - m.x as f64) * m.scale).round() as i32;
                    let sy = ((cy - m.y as f64) * m.scale).round() as i32;
                    (sx, sy)
                } else if let Some((px, py)) = pos {
                    // Fallback using portal position if monitor list is empty
                    (
                        (cx - px as f64).round() as i32,
                        (cy - py as f64).round() as i32,
                    )
                } else {
                    (cx.round() as i32, cy.round() as i32)
                };

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
        let sx = ((cx - m.x as f64) * m.scale).round() as i32;
        let sy = ((cy - m.y as f64) * m.scale).round() as i32;
        assert_eq!(sx, 805);
        assert_eq!(sy, 882);
    }
}
