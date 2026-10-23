package mosscore

import "errors"

var ErrBindingsUnavailable = errors.New("mosscore: libmoss bindings are unavailable; build with CGO_ENABLED=1 and install the platform native library (see sdks/go/bindings/README.md)")
var ErrClientClosed = errors.New("mosscore: client is closed")
