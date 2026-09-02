/* okf-context hashing port (PROFILE.md rules) — vanilla JS, no deps.
   Canonical CBOR (RFC 8949 §4.2.1, restricted types), domain-separated
   SHA-256 (ASCII domain + 0x00 + CBOR), HMAC-SHA256 with the fixture key,
   canon:v1 text normalization, PROFILE.md 2.6 frontmatter split.
   Loads as a browser global (OkfHash) or a CommonJS module (tools/). */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.OkfHash = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  // ---- SHA-256 (FIPS 180-4), sync, Uint8Array in / Uint8Array out -------
  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ];

  function sha256(bytes) {
    var len = bytes.length;
    var padLen = (((len + 9) + 63) >> 6) << 6;
    var buf = new Uint8Array(padLen);
    buf.set(bytes);
    buf[len] = 0x80;
    var bitLenHi = Math.floor((len * 8) / 0x100000000);
    var bitLenLo = (len * 8) >>> 0;
    buf[padLen - 8] = (bitLenHi >>> 24) & 0xff;
    buf[padLen - 7] = (bitLenHi >>> 16) & 0xff;
    buf[padLen - 6] = (bitLenHi >>> 8) & 0xff;
    buf[padLen - 5] = bitLenHi & 0xff;
    buf[padLen - 4] = (bitLenLo >>> 24) & 0xff;
    buf[padLen - 3] = (bitLenLo >>> 16) & 0xff;
    buf[padLen - 2] = (bitLenLo >>> 8) & 0xff;
    buf[padLen - 1] = bitLenLo & 0xff;

    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var W = new Int32Array(64);
    for (var off = 0; off < padLen; off += 64) {
      for (var t = 0; t < 16; t++) {
        var i = off + t * 4;
        W[t] = (buf[i] << 24) | (buf[i + 1] << 16) | (buf[i + 2] << 8) | buf[i + 3];
      }
      for (t = 16; t < 64; t++) {
        var w15 = W[t - 15], w2 = W[t - 2];
        var s0 = ((w15 >>> 7) | (w15 << 25)) ^ ((w15 >>> 18) | (w15 << 14)) ^ (w15 >>> 3);
        var s1 = ((w2 >>> 17) | (w2 << 15)) ^ ((w2 >>> 19) | (w2 << 13)) ^ (w2 >>> 10);
        W[t] = (W[t - 16] + s0 + W[t - 7] + s1) | 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (t = 0; t < 64; t++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[t] + W[t]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0;
        d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    var out = new Uint8Array(32);
    for (var j = 0; j < 8; j++) {
      out[j * 4] = (H[j] >>> 24) & 0xff;
      out[j * 4 + 1] = (H[j] >>> 16) & 0xff;
      out[j * 4 + 2] = (H[j] >>> 8) & 0xff;
      out[j * 4 + 3] = H[j] & 0xff;
    }
    return out;
  }

  function concat(parts) {
    var n = 0, i;
    for (i = 0; i < parts.length; i++) n += parts[i].length;
    var out = new Uint8Array(n), p = 0;
    for (i = 0; i < parts.length; i++) { out.set(parts[i], p); p += parts[i].length; }
    return out;
  }

  function hmacSha256(key, msg) {
    if (key.length > 64) key = sha256(key);
    var k = new Uint8Array(64); k.set(key);
    var ipad = new Uint8Array(64), opad = new Uint8Array(64);
    for (var i = 0; i < 64; i++) { ipad[i] = k[i] ^ 0x36; opad[i] = k[i] ^ 0x5c; }
    return sha256(concat([opad, sha256(concat([ipad, msg]))]));
  }

  // ---- encoding helpers ---------------------------------------------------
  var encoder = new TextEncoder();
  function utf8(s) { return encoder.encode(s); }
  function ascii(s) {
    var out = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c > 0x7f) throw new Error("domain string must be ASCII");
      out[i] = c;
    }
    return out;
  }
  function hex(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) s += (bytes[i] < 16 ? "0" : "") + bytes[i].toString(16);
    return s;
  }
  function hexid(bytes) { return "sha256:" + hex(bytes); }
  function compareBytes(a, b) {
    var n = Math.min(a.length, b.length);
    for (var i = 0; i < n; i++) if (a[i] !== b[i]) return a[i] - b[i];
    return a.length - b.length;
  }

  // ---- canonical CBOR (RFC 8949 §4.2.1, profile-restricted types) ---------
  function head(major, arg) {
    if (arg < 24) return new Uint8Array([(major << 5) | arg]);
    if (arg < 0x100) return new Uint8Array([(major << 5) | 24, arg]);
    if (arg < 0x10000) return new Uint8Array([(major << 5) | 25, arg >>> 8, arg & 0xff]);
    if (arg < 0x100000000) return new Uint8Array([(major << 5) | 26, (arg >>> 24) & 0xff, (arg >>> 16) & 0xff, (arg >>> 8) & 0xff, arg & 0xff]);
    throw new Error("length too large");
  }
  function cbor(obj) {
    if (obj === false) return new Uint8Array([0xf4]);
    if (obj === true) return new Uint8Array([0xf5]);
    if (obj === null || obj === undefined) return new Uint8Array([0xf6]);
    if (typeof obj === "number") {
      if (!Number.isInteger(obj) || obj < 0) throw new Error("only non-negative integers are in the profile");
      return head(0, obj);
    }
    if (obj instanceof Uint8Array) return concat([head(2, obj.length), obj]);
    if (typeof obj === "string") { var b = utf8(obj.normalize("NFC")); return concat([head(3, b.length), b]); }
    if (Array.isArray(obj)) { var parts = [head(4, obj.length)]; for (var i = 0; i < obj.length; i++) parts.push(cbor(obj[i])); return concat(parts); }
    if (typeof obj === "object") {
      var items = Object.keys(obj).map(function (k) { return [cbor(k), cbor(obj[k])]; });
      items.sort(function (x, y) { return compareBytes(x[0], y[0]) || compareBytes(x[1], y[1]); });
      var mp = [head(5, items.length)];
      for (var j = 0; j < items.length; j++) { mp.push(items[j][0]); mp.push(items[j][1]); }
      return concat(mp);
    }
    throw new Error("type not in profile: " + typeof obj);
  }

  function preimage(domain, obj) { return concat([ascii(domain), new Uint8Array([0]), cbor(obj)]); }
  function h(domain, obj) { return sha256(preimage(domain, obj)); }
  function hmacH(key, domain, obj) { return hmacSha256(key, preimage(domain, obj)); }

  // ---- canon:v1 text normalization + frontmatter split ------------------
  function normalizeText(s) {
    s = s.replace(/\r\n/g, "\n").replace(/\r/g, "\n").normalize("NFC");
    var lines = s.split("\n").map(function (ln) { return ln.replace(/[ \t]+$/, ""); });
    return lines.join("\n").replace(/\n+$/, "") + "\n";
  }
  function splitFrontmatter(text) {
    var lines = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
    if (lines[0] !== "---") throw new Error("no frontmatter block");
    var close = lines.indexOf("---", 1);
    if (close < 0) throw new Error("unterminated frontmatter");
    return { frontmatter: lines.slice(1, close).join("\n"), body: lines.slice(close + 1).join("\n") };
  }

  return {
    sha256: sha256, hmacSha256: hmacSha256, utf8: utf8, hex: hex, hexid: hexid,
    cbor: cbor, preimage: preimage, h: h, hmacH: hmacH, compareBytes: compareBytes,
    normalizeText: normalizeText, splitFrontmatter: splitFrontmatter
  };
});
