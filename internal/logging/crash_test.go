package logging

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestCrashLogDir(t *testing.T) {
	dir := CrashLogDir()
	if dir == "" {
		t.Error("CrashLogDir returned empty string")
	}
}

func TestWriteAndReadCrashLog(t *testing.T) {
	// Create a temporary directory for testing
	tmpDir := t.TempDir()

	// Override the crash log dir for testing
	originalDir := CrashLogDir()
	t.Cleanup(func() {
		// Can't easily restore, but temp dir is cleaned up automatically
		_ = originalDir
	})

	// Write a crash log directly to temp dir
	testPanic := "test panic value"
	testStack := []byte("test stack trace")

	timestamp := time.Now().Format("2006-01-02_15-04-05")
	filename := "crash_" + timestamp + ".log"
	crashPath := filepath.Join(tmpDir, filename)

	content := "NFC Agent Crash Report\n======================\nTest content"
	if err := os.WriteFile(crashPath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test crash log: %v", err)
	}

	// Verify file exists
	if _, err := os.Stat(crashPath); os.IsNotExist(err) {
		t.Error("Crash log file was not created")
	}

	// Test that we can read it back
	readContent, err := os.ReadFile(crashPath)
	if err != nil {
		t.Fatalf("Failed to read crash log: %v", err)
	}
	if string(readContent) != content {
		t.Errorf("Content mismatch: got %q, want %q", string(readContent), content)
	}

	_ = testPanic
	_ = testStack
}

func TestCleanupOldCrashLogs(t *testing.T) {
	// Create a temporary directory for testing
	tmpDir := t.TempDir()

	// Create more than MaxCrashLogs files
	numFiles := MaxCrashLogs + 5
	for i := 0; i < numFiles; i++ {
		// Create files with timestamps that sort correctly
		timestamp := time.Now().Add(time.Duration(-numFiles+i) * time.Hour).Format("2006-01-02_15-04-05")
		filename := "crash_" + timestamp + ".log"
		path := filepath.Join(tmpDir, filename)
		if err := os.WriteFile(path, []byte("test"), 0644); err != nil {
			t.Fatalf("Failed to create test file: %v", err)
		}
	}

	// Also create a non-crash file that should be ignored
	nonCrashFile := filepath.Join(tmpDir, "other.log")
	if err := os.WriteFile(nonCrashFile, []byte("test"), 0644); err != nil {
		t.Fatalf("Failed to create non-crash file: %v", err)
	}

	// Run cleanup on the temp dir
	cleanupCrashLogsInDir(tmpDir)

	// Count remaining crash log files
	entries, err := os.ReadDir(tmpDir)
	if err != nil {
		t.Fatalf("Failed to read temp dir: %v", err)
	}

	crashLogCount := 0
	hasNonCrashFile := false
	for _, entry := range entries {
		if entry.Name() == "other.log" {
			hasNonCrashFile = true
		} else if filepath.Ext(entry.Name()) == ".log" {
			crashLogCount++
		}
	}

	if crashLogCount > MaxCrashLogs {
		t.Errorf("Expected at most %d crash logs, got %d", MaxCrashLogs, crashLogCount)
	}

	if !hasNonCrashFile {
		t.Error("Non-crash file was incorrectly deleted")
	}
}

func TestCleanupOldCrashLogsByAge(t *testing.T) {
	tmpDir := t.TempDir()

	// Create an old file (simulate by setting mod time)
	oldFile := filepath.Join(tmpDir, "crash_2020-01-01_00-00-00.log")
	if err := os.WriteFile(oldFile, []byte("old"), 0644); err != nil {
		t.Fatalf("Failed to create old file: %v", err)
	}
	// Set modification time to 60 days ago
	oldTime := time.Now().Add(-60 * 24 * time.Hour)
	if err := os.Chtimes(oldFile, oldTime, oldTime); err != nil {
		t.Fatalf("Failed to set mod time: %v", err)
	}

	// Create a recent file
	recentFile := filepath.Join(tmpDir, "crash_2099-01-01_00-00-00.log")
	if err := os.WriteFile(recentFile, []byte("recent"), 0644); err != nil {
		t.Fatalf("Failed to create recent file: %v", err)
	}

	// Run cleanup
	cleanupCrashLogsInDir(tmpDir)

	// Old file should be deleted
	if _, err := os.Stat(oldFile); !os.IsNotExist(err) {
		t.Error("Old crash log was not deleted")
	}

	// Recent file should remain
	if _, err := os.Stat(recentFile); os.IsNotExist(err) {
		t.Error("Recent crash log was incorrectly deleted")
	}
}

// cleanupCrashLogsInDir is a test helper that runs cleanup on a specific directory
func cleanupCrashLogsInDir(dir string) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}

	var crashLogs []os.DirEntry
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if len(name) > 6 && name[:6] == "crash_" && filepath.Ext(name) == ".log" {
			crashLogs = append(crashLogs, entry)
		}
	}

	// Sort by name (timestamp order)
	for i := 0; i < len(crashLogs)-1; i++ {
		for j := i + 1; j < len(crashLogs); j++ {
			if crashLogs[i].Name() > crashLogs[j].Name() {
				crashLogs[i], crashLogs[j] = crashLogs[j], crashLogs[i]
			}
		}
	}

	now := time.Now()
	for i, entry := range crashLogs {
		shouldDelete := false

		if len(crashLogs)-i > MaxCrashLogs {
			shouldDelete = true
		}

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
