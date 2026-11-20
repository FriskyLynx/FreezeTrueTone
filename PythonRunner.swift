
import Foundation
import Combine

final class PythonRunner: ObservableObject {
    static let shared = PythonRunner()
    @Published private(set) var isRunning = false

    private var process: Process?
    private var inputPipe: Pipe?

    func start(strength: Double, interval: Double) {
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
        let pipe = Pipe()

        task.executableURL = python
        task.arguments = [
            "-B", script.path,
            "--strength", String(strength),
            "--interval", String(interval)
        ]
        task.currentDirectoryURL = resources
        task.standardInput = pipe

        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONHOME"] = pythonHome.path
        environment["PYTHONNOUSERSITE"] = "1"
        task.environment = environment

        task.terminationHandler = { [weak self] finished in
            DispatchQueue.main.async {
                guard let self,
                      self.process === finished else { return }

                self.inputPipe?.fileHandleForWriting.closeFile()
                self.inputPipe = nil
                self.process = nil
                self.isRunning = false
                print("Python stopped")
            }
        }

        do {
            try task.run()
            inputPipe = pipe
            process = task
            isRunning = true
            print("Python started")
        } catch {
            print("Python error:", error)
        }
    }

    // Send configuration updates to running Python
    func updateConfiguration(strength: Double, interval: Double) {
        guard process?.isRunning == true,
              let inputPipe else {
            return
        }

        let config: [String: Double] = [
            "strength": strength,
            "interval": interval
        ]

        do {
            var data = try JSONSerialization.data(
                withJSONObject: config
            )

            // Every JSON message ends with a newline
            data.append(0x0A)

            try inputPipe.fileHandleForWriting
                .write(contentsOf: data)

            print("Updated Python configuration:", config)
        } catch {
            print("Failed to send configuration:", error)
        }
    }

    func stop() {
        guard let process, process.isRunning else {
            return
        }

        process.terminate()
    }
}
