//go:build linux

package welcome

// ShowWelcome is a no-op on Linux (no tray = no welcome popup)
func ShowWelcome() {
	// Linux runs as a headless service, no popup needed
}

// ShowAbout is a no-op on Linux
func ShowAbout(version string) {
	// Linux runs as a headless service, no popup needed
}

// PromptAutostart is a no-op on Linux (headless service)
// Auto-start is handled by systemd service installation
func PromptAutostart() bool {
	return false
}
