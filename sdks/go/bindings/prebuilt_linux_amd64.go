//go:build cgo && linux && amd64

package mosscore

/*
#cgo CFLAGS: -I${SRCDIR}/include
#cgo LDFLAGS: -L${SRCDIR}/lib/linux-amd64 -lmoss -lstdc++ -ldl -lm -lpthread
*/
import "C"
