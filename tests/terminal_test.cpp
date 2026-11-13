#include "terminal.hpp"
#include <iostream>
#include <stdexcept>
void expect(const std::string& input, const std::string& output) {
    if (clean(input) != output) throw std::runtime_error("Terminal escaping mismatch.");
}
int main() {
    try {
        expect(u8"Café 東京 العربية 👩‍💻", u8"Café 東京 العربية 👩‍💻");
        expect("a\n\x1b\x7f" "b", "a   b");
        expect(u8"a\u0085\u009Bb", "a\\u0085\\u009Bb");
        expect(u8"a\u061c\u200e\u200f\u202e\u2066\u2069b", "a\\u061C\\u200E\\u200F\\u202E\\u2066\\u2069b");
        expect(u8"a\u2028\u2029b", "a\\u2028\\u2029b");
        expect("\x9b\xc0\xaf", "\\x9B\\xC0\\xAF");
        expect("\xed\xa0\x80", "\\xED\\xA0\\x80");
        expect("\xf4\x90\x80\x80", "\\xF4\\x90\\x80\\x80");
        expect("\xe2\x80", "\\xE2\\x80");
        std::cout << "UTF-8 terminal escaping passed.\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
