package logging

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"sort"
	"strings"
	"time"
)

const (
	// MaxCrashLogs is the maximum number of crash logs to keep
	MaxCrashLogs = 20
	// CrashLogMaxAge is the maximum age of crash logs before cleanup
	CrashLogMaxAge = 30 * 24 * time.Hour // 30 days
)

// CrashLogDir returns the directory for crash logs based on the platform.
func CrashLogDir() string {
	switch runtime.GOOS {
	case "darwin":
		home, _ := os.UserHomeDir()
		return filepath.Join(home, "Library", "Logs", "NFC-Agent")
	case "windows":
		appData := os.Getenv("LOCALAPPDATA")
		if appData == "" {
			appData, _ = os.UserHomeDir()
		}
		return filepath.Join(appData, "NFC-Agent", "logs")
	default: // Linux and others
		home, _ := os.UserHomeDir()
		return filepath.Join(home, ".local", "share", "nfc-agent", "logs")
	}
}

// ensureCrashLogDir creates the crash log directory if it doesn't exist.
func ensureCrashLogDir() error {
	dir := CrashLogDir()
	return os.MkdirAll(dir, 0755)
}

// WriteCrashLog writes a crash report to a timestamped file.
// Returns the path to the crash log file.
// Also triggers cleanup of old crash logs.
func WriteCrashLog(panicValue interface{}, stack []byte) (string, error) {
	if err := ensureCrashLogDir(); err != nil {
		return "", fmt.Errorf("failed to create crash log directory: %w", err)
	}

	timestamp := time.Now().Format("2006-01-02_15-04-05")
	filename := fmt.Sprintf("crash_%s.log", timestamp)
	crashFilePath := filepath.Join(CrashLogDir(), filename)

	content := fmt.Sprintf(`NFC Agent Crash Report
======================
Time: %s
Go Version: %s
OS/Arch: %s/%s

Panic Value:
%v

Stack Trace:
%s

Build Info:
%s
`,
		time.Now().Format(time.RFC3339),
		runtime.Version(),
		runtime.GOOS, runtime.GOARCH,
		panicValue,
		string(stack),
		getBuildInfo(),
	)

	if err := os.WriteFile(crashFilePath, []byte(content), 0644); err != nil {
		return "", fmt.Errorf("failed to write crash log: %w", err)
	}

	// Clean up old crash logs in background
	go cleanupOldCrashLogs()

	return crashFilePath, nil
}

// getBuildInfo returns build information if available.
func getBuildInfo() string {
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return "Build info not available"
	}
	return info.String()
}

// RecoverAndLog recovers from a panic, logs it to a file, and optionally re-panics.
// Use this as: defer logging.RecoverAndLog("context", true)
// Set rePanic to true for critical goroutines where you want the app to crash after logging.
func RecoverAndLog(context string, rePanic bool) {
	if r := recover(); r != nil {
		stack := debug.Stack()

		// Send to Sentry if enabled
		CapturePanic(r, stack, context)

		// Log to in-memory logger
		Error(CatSystem, fmt.Sprintf("PANIC in %s: %v", context, r), map[string]any{
			"panic": fmt.Sprintf("%v", r),
			"stack": string(stack),
		})

		// Write crash log to file
		crashFile, err := WriteCrashLog(r, stack)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to write crash log: %v\n", err)
		} else {
			fmt.Fprintf(os.Stderr, "Crash log written to: %s\n", crashFile)
		}

		// Print to stderr for immediate visibility
		fmt.Fprintf(os.Stderr, "\n=== PANIC in %s ===\n%v\n\nStack trace:\n%s\n", context, r, string(stack))

		if rePanic {
			panic(r)
		}
	}
}

// RecoverAndLogFunc is like RecoverAndLog but calls a callback before optionally re-panicking.
// Useful for cleanup or notifying other components.
func RecoverAndLogFunc(context string, rePanic bool, onPanic func(panicValue interface{}, crashFile string)) {
	if r := recover(); r != nil {
		stack := debug.Stack()

		// Send to Sentry if enabled
		CapturePanic(r, stack, context)

		// Log to in-memory logger
		Error(CatSystem, fmt.Sprintf("PANIC in %s: %v", context, r), map[string]any{
			"panic": fmt.Sprintf("%v", r),
			"stack": string(stack),
		})

		// Write crash log to file
		crashFile, err := WriteCrashLog(r, stack)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to write crash log: %v\n", err)
			crashFile = ""
		} else {
			fmt.Fprintf(os.Stderr, "Crash log written to: %s\n", crashFile)
		}

		// Print to stderr for immediate visibility
		fmt.Fprintf(os.Stderr, "\n=== PANIC in %s ===\n%v\n\nStack trace:\n%s\n", context, r, string(stack))

		if onPanic != nil {
			onPanic(r, crashFile)
		}

		if rePanic {
			panic(r)
		}
	}
}

// GetCrashLogs returns a list of recent crash log files (only crash_*.log files).
func GetCrashLogs(limit int) ([]CrashLogInfo, error) {
	dir := CrashLogDir()
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return []CrashLogInfo{}, nil
		}
		return nil, err
	}

	var logs []CrashLogInfo
	// Iterate in reverse to get newest first
	for i := len(entries) - 1; i >= 0 && len(logs) < limit; i-- {
		entry := entries[i]
		if entry.IsDir() {
			continue
		}
		// Only include crash log files (crash_*.log)
		name := entry.Name()
		if !strings.HasPrefix(name, "crash_") || !strings.HasSuffix(name, ".log") {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		logs = append(logs, CrashLogInfo{
			Name:    name,
			Path:    filepath.Join(dir, name),
			Size:    info.Size(),
			ModTime: info.ModTime(),
		})
	}
	return logs, nil
}

// CrashLogInfo contains metadata about a crash log file.
type CrashLogInfo struct {
	Name    string    `json:"name"`
	Path    string    `json:"path"`
	Size    int64     `json:"size"`
	ModTime time.Time `json:"modTime"`
}

// ReadCrashLog reads the contents of a crash log file.
func ReadCrashLog(filename string) (string, error) {
	// Ensure the filename is just a filename, not a path (security)
	if filepath.Base(filename) != filename {
		return "", fmt.Errorf("invalid filename")
	}

	path := filepath.Join(CrashLogDir(), filename)
	content, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return string(content), nil
}

// cleanupOldCrashLogs removes old crash logs to prevent disk space buildup.
// Keeps at most MaxCrashLogs files and removes any older than CrashLogMaxAge.
func cleanupOldCrashLogs() {
	dir := CrashLogDir()
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}

	// Filter to only crash log files (crash_*.log)
	var crashLogs []os.DirEntry
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		if strings.HasPrefix(entry.Name(), "crash_") && strings.HasSuffix(entry.Name(), ".log") {
			crashLogs = append(crashLogs, entry)
		}
	}

	// Sort by name (which includes timestamp, so newest last)
	sort.Slice(crashLogs, func(i, j int) bool {
		return crashLogs[i].Name() < crashLogs[j].Name()
	})

	now := time.Now()

	// Delete old logs (keep at most MaxCrashLogs, delete anything older than CrashLogMaxAge)
	for i, entry := range crashLogs {
		shouldDelete := false

		// Delete if we have too many (keep the newest MaxCrashLogs)
		if len(crashLogs)-i > MaxCrashLogs {
			shouldDelete = true
		}

		// Also delete if older than max age
		if info, err := entry.Info(); err == nil {
			if now.Sub(info.ModTime()) > CrashLogMaxAge {
				shouldDelete = true
			}
		}

		if shouldDelete {
			_ = os.Remove(filepath.Join(dir, entry.Name()))
		}
	}
}
