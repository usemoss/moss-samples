package main

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestSafeArchiveTarget(t *testing.T) {
	root := t.TempDir()

	target, err := safeArchiveTarget(root, "include/libmoss.h")
	if err != nil {
		t.Fatalf("safeArchiveTarget returned an error: %v", err)
	}
	want := filepath.Join(root, "include", "libmoss.h")
	if target != want {
		t.Fatalf("safeArchiveTarget() = %q, want %q", target, want)
	}

	for _, input := range []string{"..", "../outside", "/outside"} {
		if _, err := safeArchiveTarget(root, input); err == nil {
			t.Errorf("safeArchiveTarget(%q) succeeded, want error", input)
		}
	}
}

func TestNativeReleaseTag(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "version.go"), []byte("package mosscore\n\nconst NativeLibReleaseTag = \"c-sdk-v1.2.3\"\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	tag, err := nativeReleaseTag(root)
	if err != nil {
		t.Fatalf("nativeReleaseTag returned an error: %v", err)
	}
	if tag != "c-sdk-v1.2.3" {
		t.Fatalf("nativeReleaseTag() = %q, want c-sdk-v1.2.3", tag)
	}
}

func TestInstallReceipt(t *testing.T) {
	path := filepath.Join(t.TempDir(), installReceiptName)
	if err := writeReceipt(path, "libmoss-v0.9.0-x86_64-unknown-linux-gnu.tar.gz", "abc123"); err != nil {
		t.Fatalf("writeReceipt returned an error: %v", err)
	}
	if !receiptMatches(path, "libmoss-v0.9.0-x86_64-unknown-linux-gnu.tar.gz", "abc123") {
		t.Fatal("receiptMatches() = false, want true")
	}
	if receiptMatches(path, "libmoss-v0.9.0-x86_64-unknown-linux-gnu.tar.gz", "different") {
		t.Fatal("receiptMatches() = true for a different checksum, want false")
	}
}

func TestVendorArgs(t *testing.T) {
	if got, want := vendorArgs(""), []string{"mod", "vendor"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("vendorArgs(\"\") = %v, want %v", got, want)
	}
	if got, want := vendorArgs("/work/go.work"), []string{"work", "vendor"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("vendorArgs(workspace) = %v, want %v", got, want)
	}
}

func TestCopyFileDoesNotTruncateDestinationOnSourceError(t *testing.T) {
	dir := t.TempDir()
	dest := filepath.Join(dir, "libmoss.a")
	if err := os.WriteFile(dest, []byte("known-good"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := copyFile(filepath.Join(dir, "missing"), dest); err == nil {
		t.Fatal("copyFile succeeded with a missing source")
	}
	contents, err := os.ReadFile(dest)
	if err != nil {
		t.Fatal(err)
	}
	if string(contents) != "known-good" {
		t.Fatalf("destination = %q, want known-good", contents)
	}
}

func TestIsModuleCacheDir(t *testing.T) {
	cacheDir := t.TempDir()
	t.Setenv("GOMODCACHE", cacheDir)

	inside := filepath.Join(cacheDir, "github.com", "usemoss", "moss")
	if !isModuleCacheDir(inside) {
		t.Fatalf("isModuleCacheDir(%q) = false, want true", inside)
	}
	if isModuleCacheDir(filepath.Dir(cacheDir)) {
		t.Fatal("isModuleCacheDir() = true outside the module cache")
	}
}
