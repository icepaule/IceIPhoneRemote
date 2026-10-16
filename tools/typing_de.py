"""Type text on an iPhone whose hardware-keyboard layout is German while the board sends US HID codes.
Verified on iOS 27: '@' = Option+L, '#' = the US backslash key, y and z are swapped."""
SWAP = {"y": "z", "z": "y", "Y": "Z", "Z": "Y", "#": "\\", "-": "/", "_": "?", "/": "&", ":": ">", ";": "<", "\"": "@",
        "&": "^", "(": "*", ")": "(", "=": ")", "?": "_", "*": "}", "+": "]"}   # German char -> US key that produces it

def type_de(remote, text):
    buf = ""
    def flush():
        nonlocal buf
        if buf: remote.cmd("type " + buf); buf = ""
    for ch in text:
        if ch == "@": flush(); remote.cmd("key alt+l")
        else: buf += SWAP.get(ch, ch)
    flush()
