//
//  PythonRunner.swift
//  FreezeTrueTone
//
//  Created by frisky (aurardian) on 20.11.26.
//


import Foundation
import Combine

class PythonRunner: ObservableObject {
    @Published private(set) var isRunning = false

    private var process: Process?

    func start() {
        guard !isRunning,
              let resources = Bundle.main.resourceURL else {
            return
        }

        let pythonHome = resources
            .appendingPathComponent("python-runtime")

        let python = pythonHome
            .appendingPathComponent("bin/python3")

        let script = resources
            .appendingPathComponent("truetone_freeze-2.py")

        let task = Process()
        task.executableURL = python
        task.arguments = ["-B", script.path]
        task.currentDirectoryURL = resources

        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONHOME"] = pythonHome.path
        environment["PYTHONNOUSERSITE"] = "1"
        task.environment = environment

        // Automatically detect when Python exits
        task.terminationHandler = { [weak self] finished in
            DispatchQueue.main.async {
                guard let self,
                      self.process === finished else { return }

                self.process = nil
                self.isRunning = false
                print("Python stopped")
            }
        }

        do {
            try task.run()
            process = task
            isRunning = true
            print("Python started, PID:", task.processIdentifier)
        } catch {
            print("Python error:", error)
        }
    }

    func stop() {
        guard let process, process.isRunning else {
            return
        }

        process.terminate()
    }
}
