//go:build cgo && darwin && arm64

package mosscore

/*
#cgo CFLAGS: -I${SRCDIR}/include
#cgo LDFLAGS: -L${SRCDIR}/lib/darwin-arm64 -lmoss -lc++ -framework Security -framework SystemConfiguration
*/
import "C"
