use serde::Serialize;
use std::sync::Mutex;
use sysinfo::System;

pub struct TelemetryState {
    system: Mutex<System>,
}

impl TelemetryState {
    pub fn new() -> Self {
        let system = System::new_all().unwrap_or_else(|_| {
            System::new().unwrap_or_else(|_| panic!("failed to initialize system telemetry"))
        });

        Self {
            system: Mutex::new(system),
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SystemSnapshot {
    pub cpu_usage: f32,
    pub memory_usage: u64,
    pub memory_total: u64,
    pub uptime: u64,
    pub hostname: String,
    pub os: String,
    pub cpu_name: String,
}

#[tauri::command]
pub fn get_system_snapshot(
    state: tauri::State<'_, TelemetryState>,
) -> Result<SystemSnapshot, String> {
    let mut system = state
        .system
        .lock()
        .map_err(|_| "system telemetry is unavailable".to_string())?;

    system.refresh_cpu_usage();
    system.refresh_memory();

    let cpu_name = system
        .cpus()
        .first()
        .map(|cpu| cpu.brand().trim().to_string())
        .unwrap_or_default();

    Ok(SystemSnapshot {
        cpu_usage: system.global_cpu_usage(),
        memory_usage: system.used_memory(),
        memory_total: system.total_memory(),
        uptime: System::uptime().unwrap_or(0),
        hostname: System::host_name().unwrap_or_else(|_| "unknown".to_string()),
        os: System::long_os_version().unwrap_or_else(|_| "Windows".to_string()),
        cpu_name,
    })
}
