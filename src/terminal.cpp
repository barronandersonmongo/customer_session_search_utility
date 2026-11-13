#include "terminal.hpp"
#include <cstdint>
#include <cstdio>

std::string clean(std::string_view text) {
    std::string output;
    auto byte_escape = [&](unsigned char value) {
        char escaped[5];
        std::snprintf(escaped, sizeof(escaped), "\\x%02X", value);
        output += escaped;
    };
    for (size_t i = 0; i < text.size();) {
        const auto lead = static_cast<unsigned char>(text[i]);
        if (lead < 128) {
            output += lead < 32 || lead == 127 ? ' ' : static_cast<char>(lead);
            ++i;
            continue;
        }
        size_t length = lead >= 0xc2 && lead <= 0xdf ? 2 : lead >= 0xe0 && lead <= 0xef ? 3 :
                        lead >= 0xf0 && lead <= 0xf4 ? 4 : 0;
        uint32_t cp = length ? lead & ((1u << (7 - length)) - 1) : 0;
        bool valid = length && i + length <= text.size();
        for (size_t j = 1; valid && j < length; ++j) {
            const auto byte = static_cast<unsigned char>(text[i + j]);
            if ((byte & 0xc0) != 0x80) valid = false;
            else cp = (cp << 6) | (byte & 0x3f);
        }
        if (!valid || (length == 2 && cp < 0x80) || (length == 3 && cp < 0x800) ||
            (length == 4 && cp < 0x10000) || (cp >= 0xd800 && cp <= 0xdfff) || cp > 0x10ffff) {
            byte_escape(lead);
            ++i;
            continue;
        }
        const bool hazardous = (cp >= 0x80 && cp <= 0x9f) || cp == 0x61c || cp == 0x200e || cp == 0x200f ||
                               (cp >= 0x202a && cp <= 0x202e) || (cp >= 0x2066 && cp <= 0x2069) ||
                               cp == 0x2028 || cp == 0x2029;
        if (hazardous) {
            char escaped[7];
            std::snprintf(escaped, sizeof(escaped), "\\u%04X", cp);
            output += escaped;
        } else output.append(text.substr(i, length));
        i += length;
    }
    return output;
}
