//
//  FreezeTrueToneApp.swift
//  FreezeTrueTone
//
//  Created by frisky (aurardian) on 19.11.26.
//

import SwiftUI
import CoreGraphics
@main
struct FreezeTrueToneApp: App {
    @StateObject private var python = PythonRunner()
    var body: some Scene {
        MenuBarExtra("Test Utility", systemImage: "sun.max") {
            Text("Hello bro")
            Divider()
            Button("Start Script"){
                python.start()
            }
            .disabled(python.isRunning)
            
            Divider()
            Button("Stop Script"){
                python.stop()
            }
            .disabled(!python.isRunning)
            Divider()
            Button("Quit App"){
                python.stop()
                NSApplication.shared.terminate(nil)
            }
        }
        .menuBarExtraStyle(.menu)
    }
    
    func runPython() {
        guard let resources = Bundle.main.resourceURL,
              let executableDir = Bundle.main.executableURL?
                  .deletingLastPathComponent() else {
            return
        }

        let pythonHome = resources
            .appendingPathComponent("python-runtime")

        let python = pythonHome
            .appendingPathComponent("bin/python3")

        let script = resources
            .appendingPathComponent("truetone_freeze-2.py")

        let process = Process()
        process.executableURL = python
        process.arguments = ["-B", script.path]
        process.currentDirectoryURL = resources

        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONHOME"] = pythonHome.path
        environment["PYTHONNOUSERSITE"] = "1"
        process.environment = environment

        do {
            try process.run()
            print("Bundled Python started")
        } catch {
            print("Python error:", error)
        }
    }
}
