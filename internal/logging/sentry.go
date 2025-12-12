package logging

import (
	"fmt"
	"os"
	"time"

	"github.com/getsentry/sentry-go"
)

// Default Sentry DSN for crash reporting
const defaultSentryDSN = "https://75a5f0bcc72132040f5bb6ac2f8c09cd@o1102514.ingest.us.sentry.io/4510518666199040"

var sentryEnabled bool

// InitSentry initializes Sentry for crash reporting.
// Opt-in: enabled via user settings or NFC_AGENT_SENTRY=1 environment variable.
// DSN can be overridden via NFC_AGENT_SENTRY_DSN environment variable.
// Returns true if Sentry was successfully initialized.
func InitSentry(version string, crashReportingEnabled bool) bool {
	// Check environment variable override first
	envEnabled := os.Getenv("NFC_AGENT_SENTRY") == "1"
	envDisabled := os.Getenv("NFC_AGENT_SENTRY") == "0"

	// Determine if enabled: env var takes precedence, then settings
	enabled := crashReportingEnabled
	if envEnabled {
		enabled = true
	} else if envDisabled {
		enabled = false
	}

	if !enabled {
		return false
	}

	// Allow DSN override, otherwise use default
	dsn := os.Getenv("NFC_AGENT_SENTRY_DSN")
	if dsn == "" {
		dsn = defaultSentryDSN
	}

	err := sentry.Init(sentry.ClientOptions{
		Dsn:              dsn,
		Release:          "nfc-agent@" + version,
		Environment:      getEnvironment(),
		AttachStacktrace: true,
		// Sample rate for performance monitoring (disabled by default)
		TracesSampleRate: 0.0,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Failed to initialize Sentry: %v\n", err)
		return false
	}

	sentryEnabled = true
	return true
}

// getEnvironment returns the environment name for Sentry.
func getEnvironment() string {
	env := os.Getenv("NFC_AGENT_ENVIRONMENT")
	if env != "" {
		return env
	}
	return "production"
}

// SentryEnabled returns whether Sentry is currently enabled.
func SentryEnabled() bool {
	return sentryEnabled
}

// FlushSentry flushes any buffered events to Sentry.
// Call this before application exit.
func FlushSentry(timeout time.Duration) {
	if sentryEnabled {
		sentry.Flush(timeout)
	}
}

// CapturePanic sends a panic to Sentry along with the stack trace.
// This should be called from recover() handlers.
func CapturePanic(panicValue interface{}, stack []byte, context string) {
	if !sentryEnabled {
		return
	}

	sentry.WithScope(func(scope *sentry.Scope) {
		scope.SetTag("panic_context", context)
		scope.SetExtra("stack_trace", string(stack))
		scope.SetLevel(sentry.LevelFatal)

		switch v := panicValue.(type) {
		case error:
			sentry.CaptureException(v)
		case string:
			sentry.CaptureMessage(v)
		default:
			sentry.CaptureMessage(fmt.Sprintf("%v", v))
		}
	})

	// Flush immediately for panics since app may crash
	sentry.Flush(2 * time.Second)
}

// CaptureError sends an error to Sentry.
func CaptureError(err error, context string, data map[string]interface{}) {
	if !sentryEnabled || err == nil {
		return
	}

	sentry.WithScope(func(scope *sentry.Scope) {
		scope.SetTag("error_context", context)
		for k, v := range data {
			scope.SetExtra(k, v)
		}
		sentry.CaptureException(err)
	})
}

// CaptureMessage sends a message to Sentry.
func CaptureMessage(message string, level sentry.Level, data map[string]interface{}) {
	if !sentryEnabled {
		return
	}

	sentry.WithScope(func(scope *sentry.Scope) {
		scope.SetLevel(level)
		for k, v := range data {
			scope.SetExtra(k, v)
		}
		sentry.CaptureMessage(message)
	})
}
