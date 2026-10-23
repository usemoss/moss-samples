//go:build cgo && linux && arm64

package mosscore

/*
#cgo CFLAGS: -I${SRCDIR}/include
#cgo LDFLAGS: -L${SRCDIR}/lib/linux-arm64 -lmoss -lstdc++ -ldl -lm -lpthread
*/
import "C"
