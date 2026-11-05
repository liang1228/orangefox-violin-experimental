"""Host regression of actual vold source fragments; no Android/key execution."""
import argparse
import json
from pathlib import Path
import subprocess


VOLD_COMMIT = "a164ba05c5fef288059774a776b2e6e1119957cf"


def run(args, expected=0):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=60)
    if result.returncode != expected:
        raise RuntimeError(f"Exit {result.returncode}, expected {expected}: {args}\n"
                           f"{result.stdout}\n{result.stderr}")
    return result.stdout


def default_token(source):
    start = source.index("android::keystore::copySqliteDb(); // early copy db for keystore")
    start = source.index("\n", start)
    end = source.index("\n\t}", start)
    return source[start:end]


def metadata_reader(source):
    start = source.index("static bool read_key(")
    end = source.index("\nstatic bool get_number_of_sectors(", start)
    return source[start:end]


def keymaster_begin(source):
    start = source.index("static KeymasterOperation BeginKeymasterOp(")
    end = source.index("\nstatic bool encryptWithKeymasterKey(", start)
    return source[start:end]


TOKEN_HARNESS = r'''
#include <cstring>
#include <string>
int main() {
    const int PASSWORD_TOKEN_SIZE = 32;
    unsigned char password_token[PASSWORD_TOKEN_SIZE];
    // A deterministic nonzero stack sample exposes the old partial copy.
    memset(password_token, 0xa5, sizeof(password_token));
    SOURCE_FRAGMENT
    const std::string expected = "default-password";
    for (int i = 0; i < PASSWORD_TOKEN_SIZE; ++i) {
        auto want = i < int(expected.size()) ? unsigned(expected[i]) : 0u;
        if (password_token[i] != want) return 1;
    }
    return 0;
}
'''


METADATA_HARNESS = r'''
#include <algorithm>
#include <iostream>
#include <string>
#include <vector>
#define LOG(level) std::cerr
using KeyBuffer = std::vector<char>;
struct KeyGeneration { bool allow_gen; };
const int kEmptyAuthentication = 0;
static std::vector<std::string> calls;
static bool directory_exists, retrieval_ok;
bool pathExists(const std::string&) { calls.push_back("exists"); return directory_exists; }
bool MkdirsSync(const std::string&, unsigned) {
    calls.push_back("mkdir"); directory_exists = true; return true;
}
bool retrieveKey(const std::string&, int, KeyBuffer*) {
    calls.push_back("retrieve"); return retrieval_ok;
}
bool retrieveOrGenerateKey(const std::string&, const std::string&, int,
                          const KeyGeneration&, KeyBuffer*) {
    calls.push_back("retrieveOrGenerate"); return retrieval_ok;
}
namespace android { namespace base {
bool GetBoolProperty(const char*, bool) { return true; }
} }
struct Keymaster { static void deleteAllKeys() { calls.push_back("delete"); } };
SOURCE_FRAGMENT
void reset(bool exists, bool ok = true) {
    calls.clear(); directory_exists = exists; retrieval_ok = ok;
}
int main() {
    KeyBuffer key;
    reset(false);
    if (read_key("/synthetic", {false}, &key) || directory_exists ||
        calls != std::vector<std::string>{"exists"}) return 1;
    reset(true);
    if (!read_key("/synthetic", {false}, &key) ||
        calls != std::vector<std::string>{"exists", "retrieve"}) return 2;
    reset(true, false);
    if (read_key("/synthetic", {false}, &key) ||
        calls != std::vector<std::string>{"exists", "retrieve"}) return 3;
    reset(false);
    if (read_key("", {false}, &key) || !calls.empty()) return 4;
    // Preserve the existing provisioning path when generation is requested.
    reset(false);
    if (!read_key("/synthetic", {true}, &key) || !directory_exists ||
        calls != std::vector<std::string>{"mkdir", "exists", "retrieveOrGenerate"}) return 5;
    return 0;
}
'''


KEYMASTER_HARNESS = r'''
#include <iostream>
#include <mutex>
#include <optional>
#include <string>
#define LOG(level) std::cerr
#define PLOG(level) std::cerr
#define TEMP_FAILURE_RETRY(expression) (expression)
namespace km {
struct AuthorizationSet {
    const int* begin() const { return nullptr; }
    const int* end() const { return nullptr; }
    void append(const int*, const int*) {}
};
}
static bool read_ok, begin_ok, write_ok, upgrade_needed;
static int writes, begins;
static std::string written_path;
static std::mutex key_upgrade_lock;
static const char* kFn_keymaster_key_blob = "keymaster_key_blob";
// Check the optional on dereference, rather than invoking undefined behavior
// in the original implementation's negative control.
struct Upgrade {
    std::optional<std::string> value;
    explicit operator bool() const { return value.has_value(); }
    const std::string& operator*() const { return value.value(); }
};
struct KeymasterOperation {
    bool ok = false;
    Upgrade upgrade;
    explicit operator bool() const { return ok; }
    Upgrade getUpgradedBlob() const { return upgrade; }
};
struct Keymaster {
    KeymasterOperation begin(const std::string&, const km::AuthorizationSet&,
                             km::AuthorizationSet*) {
        ++begins;
        return {begin_ok, {upgrade_needed ? std::optional<std::string>("fixture") : std::nullopt}};
    }
};
int mkdir(const char*, unsigned) { return 0; }  // Never call the host filesystem.
bool readFileToString(const std::string&, std::string*) { return read_ok; }
bool writeStringToFile(const std::string&, const std::string& path) {
    ++writes; written_path = path; return write_ok;
}
SOURCE_FRAGMENT
void reset(bool upgraded, bool read = true, bool begin = true, bool write = true) {
    read_ok = read; begin_ok = begin; write_ok = write; upgrade_needed = upgraded;
    writes = begins = 0; written_path.clear();
}
int main() {
    Keymaster keymaster;
    km::AuthorizationSet params, output;
    try {
        reset(false);
        if (!BeginKeymasterOp(keymaster, "/synthetic", params, params, &output) || writes) return 2;
        reset(true);
        if (!BeginKeymasterOp(keymaster, "/synthetic", params, params, &output) ||
            writes != 1 || written_path != "/tmp/keymaster_key_blob/keymaster_key_blob") return 3;
        reset(false, false);
        if (BeginKeymasterOp(keymaster, "/synthetic", params, params, &output) || begins || writes) return 4;
        reset(false, true, false);
        if (BeginKeymasterOp(keymaster, "/synthetic", params, params, &output) || writes) return 5;
        reset(true, true, true, false);
        if (BeginKeymasterOp(keymaster, "/synthetic", params, params, &output) || writes != 1) return 6;
    } catch (const std::bad_optional_access&) {
        return 1;
    }
    return 0;
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vold-source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    assert run(["git", "-C", args.vold_source, "rev-parse", "HEAD"]).strip() == VOLD_COMMIT
    args.output.mkdir(parents=True, exist_ok=False)
    for name, relative, extract, harness in (
        ("default-token", "Decrypt.cpp", default_token, TOKEN_HARNESS),
        ("metadata-reader", "MetadataCrypt.cpp", metadata_reader, METADATA_HARNESS),
        ("keymaster-begin", "KeyStorage.cpp", keymaster_begin, KEYMASTER_HARNESS),
    ):
        fixed = extract((args.vold_source / relative).read_text())
        original = extract(run(["git", "-C", args.vold_source, "show", f"HEAD:{relative}"]))
        for variant, fragment, expected in (("fixed", fixed, 0), ("original", original, 1)):
            source = args.output / f"{name}-{variant}.cpp"
            program = args.output / f"{name}-{variant}"
            source.write_text(harness.replace("SOURCE_FRAGMENT", fragment))
            run(["c++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 source, "-o", program])
            run([program], expected=expected)
    result = {
        "vold_commit": VOLD_COMMIT,
        "default_token_zero_padding_pass": True,
        "original_partial_copy_control_fails": True,
        "metadata_reader_five_cases_pass": True,
        "original_missing_key_mkdir_control_fails": True,
        "keymaster_begin_five_cases_pass": True,
        "original_empty_upgrade_control_fails": True,
        "real_key_files_used": False, "android_program_executed": False,
        "decryption_verified": False,
    }
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
