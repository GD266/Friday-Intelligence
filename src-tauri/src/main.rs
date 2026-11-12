use tauri::Manager;

fn main() {
  tauri::Builder::default()
    .setup(|app| {
      // Initialize any plugins or state here
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error running tauri application");
}