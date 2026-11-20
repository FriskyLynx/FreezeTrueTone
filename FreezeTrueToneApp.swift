//
//  FreezeTrueToneApp.swift
//  FreezeTrueTone
//
//  Created by frisky (aurardian) on 19.11.26.
//

import SwiftUI
import CoreGraphics
import ServiceManagement
@main
struct FreezeTrueToneApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self)
    private var appDelegate

    @StateObject private var python = PythonRunner.shared
    @AppStorage("strength") private var strength = 0.75
    @AppStorage("interval") private var interval = 5.0
    @State private var launchAtLogin =
        SMAppService.mainApp.status == .enabled

    @State private var loginItemError: String?
    private var strengthBinding: Binding<Double> {
            Binding(
                get: { strength },
                set: { newValue in
                    strength = newValue
                    python.updateConfiguration(
                        strength: newValue,
                        interval: interval
                    )
                }
            )
        }
    private var intervalBinding: Binding<Double> {
           Binding(
               get: { interval },
               set: { newValue in
                   interval = newValue
                   python.updateConfiguration(
                       strength: strength,
                       interval: newValue
                   )
               }
           )
       }
    var body: some Scene {
        MenuBarExtra {
            VStack(alignment: .leading, spacing: 12) {
                Text("Freeze True Tone, made by Frisky")
                
                Divider()
                
                Toggle("Launch at Login", isOn: Binding(
                    get: { launchAtLogin },
                    set: { enabled in
                        do {
                            if enabled {
                                try SMAppService.mainApp.register()
                            } else {
                                try SMAppService.mainApp.unregister()
                            }

                            launchAtLogin =
                                SMAppService.mainApp.status == .enabled

                            loginItemError = nil

                        } catch {
                            launchAtLogin =
                                SMAppService.mainApp.status == .enabled

                            loginItemError = error.localizedDescription
                            print("Login item error:", error)
                        }
                    }
                ))

                if let loginItemError {
                    Text(loginItemError)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
                
                Button("Start True Tone") {
                    python.start(
                        strength: strength,
                        interval: interval
                    )
                }
                .disabled(python.isRunning)
                
                Button("Stop True Tone") {
                    python.stop()
                }
                .disabled(!python.isRunning)
                
                Divider()
                
                VStack(alignment: .leading) {
                    Text("Correction Strength: \(strength, specifier: "%.2f")")
                    
                    Slider(
                        value: strengthBinding,
                        in: 0...2,
                        step: 0.05
                    )
                }
                
                Menu("Configuration") {
                    
                    Picker("Update Interval", selection: intervalBinding) {
                        Text("1 second").tag(1.0)
                        Text("2 seconds").tag(2.0)
                        Text("5 seconds").tag(5.0)
                        Text("10 seconds").tag(10.0)
                    }
                }
                Divider()
                Button("Quit App"){
                    python.stop()
                    NSApplication.shared.terminate(nil)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .frame(width: 260)
            .onAppear {
                launchAtLogin = SMAppService.mainApp.status == .enabled
            }
        }label: {
                Image(systemName: python.isRunning
                      ? "sun.max.fill"
                      : "sun.max")
            }
            .menuBarExtraStyle(.window)
            
        
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
