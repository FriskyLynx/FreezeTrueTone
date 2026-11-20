//
//  AppDelegate.swift
//  FreezeTrueTone
//
//  Created by frisky on 20.11.26.
//


import AppKit
import ServiceManagement

final class AppDelegate: NSObject, NSApplicationDelegate {

    func applicationDidFinishLaunching(_ notification: Notification) {

        // Only start Python if Launch at Login is enabled
        guard SMAppService.mainApp.status == .enabled else {
            return
        }

        // Read saved configuration
        let defaults = UserDefaults.standard

        let strength = defaults.object(forKey: "strength")
            as? Double ?? 0.75

        let interval = defaults.object(forKey: "interval")
            as? Double ?? 5.0

        // Start Python automatically
        PythonRunner.shared.start(
            strength: strength,
            interval: interval
        )

        print("FreezeTrueTone started automatically")
    }
}
