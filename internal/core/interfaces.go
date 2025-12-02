package core

// SmartCardContext represents a PC/SC context for listing readers
type SmartCardContext interface {
	ListReaders() ([]string, error)
	Connect(reader string, shareMode uint32, protocol uint32) (SmartCard, error)
	Release() error
}

// SmartCard represents a connected smart card for transmitting commands
type SmartCard interface {
	Transmit(cmd []byte) ([]byte, error)
	Status() (SmartCardStatus, error)
	Disconnect(disposition uint32) error
}

// SmartCardStatus represents the status of a smart card
type SmartCardStatus struct {
	Reader         string
	State          uint32
	ActiveProtocol uint32
	Atr            []byte
}

// ContextFactory creates SmartCardContext instances
// This allows for dependency injection and mocking in tests
type ContextFactory interface {
	EstablishContext() (SmartCardContext, error)
}

// DefaultContextFactory is the production factory that uses real PC/SC
type DefaultContextFactory struct{}

// CardOperations defines the interface for card-related operations
// Used for dependency injection and mocking in tests
type CardOperations interface {
	GetCardUID(readerName string) (*Card, error)
	WriteData(readerName string, data []byte, dataType string) error
	WriteDataWithURL(readerName string, data []byte, dataType string, url string) error
	EraseCard(readerName string) error
	LockCard(readerName string) error
	SetPassword(readerName string, password []byte, pack []byte, startPage byte) error
	RemovePassword(readerName string, password []byte) error
	WriteMultipleRecords(readerName string, records []NDEFRecord) error
}

// ReaderOperations defines the interface for reader-related operations
type ReaderOperations interface {
	ListReaders() []Reader
}
