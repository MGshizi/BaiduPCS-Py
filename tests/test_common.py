import time
import os
import io
import tempfile

import requests

from baidupcs_py.common import constant
from baidupcs_py.common.number import u64_to_u8x8, u8x8_to_u64
from baidupcs_py.common.io import (
    ENCRYPT_HEAD_LEN,
    total_len,
    ChunkIO,
    RangeRequestIO,
    SimpleEncryptIO,
    ChaCha20EncryptIO,
    AES256CBCEncryptIO,
    to_decryptio,
    rapid_upload_params,
)
from baidupcs_py.common.crypto import (
    padding_key,
    padding_size,
    random_bytes,
    calu_file_md5,
    SimpleCryptography,
    ChaCha20Cryptography,
    AES256CBCCryptography,
)
from baidupcs_py.commands.upload import EncryptType


def test_rangerequestio():
    url = "http://baidu.com"
    io = RangeRequestIO("GET", url, max_chunk_size=30)

    b = b""
    while True:
        cn = io.read(10)
        if not cn:
            break
        b += cn

    o = requests.get(url).content
    assert b == o


def test_calu_file_md5():
    _, path = tempfile.mkstemp()
    fd = open(path, "w")
    try:
        fd.write("asdf")
        r = calu_file_md5(path)
    finally:
        os.remove(path)
    assert r


def test_simplecryptography():
    key = os.urandom(32)
    c = SimpleCryptography(key)
    buf = os.urandom(100)
    enc = c.encrypt(buf)
    dec = c.decrypt(enc)
    assert buf == dec


def test_chacha20cryptography():
    key = os.urandom(32)
    nonce = os.urandom(16)
    c = ChaCha20Cryptography(key, nonce)
    buf = os.urandom(100)
    enc = c.encrypt(buf)
    dec = c.decrypt(enc)
    assert buf == dec


def test_aescryptography():
    key = os.urandom(32)
    iv = os.urandom(16)
    c = AES256CBCCryptography(key, iv)
    buf = b"a" * 16 * 2

    enc = c.encrypt(buf)
    print("enc:", enc, len(enc))
    enc += c._encryptor.finalize()

    dec = c.decrypt(enc[:16])
    print("dec:", dec, len(dec))
    dec += c.decrypt(enc[16:])
    print("dec:", dec, len(dec))
    dec += c._decryptor.finalize()
    assert buf == dec


def test_simplecryptography_time():
    key = os.urandom(32)
    c = SimpleCryptography(key)
    buf = b"a" * 1024 * 1024 * 100
    start = time.time()
    c.encrypt(buf)
    end = time.time()
    print("100M:", end - start)


def test_chacha20cryptography_time():
    key = os.urandom(32)
    nonce = os.urandom(16)
    c = ChaCha20Cryptography(key, nonce)
    buf = b"a" * 1024 * 1024 * 100
    start = time.time()
    c.encrypt(buf)
    end = time.time()
    print("100M:", end - start)


def test_aes256cbccryptography_time():
    key = os.urandom(32)
    iv = os.urandom(16)
    c = AES256CBCCryptography(key, iv)
    buf = b"a" * 1024 * 1024 * 100
    start = time.time()
    enc = c.encrypt(buf)
    end = time.time()
    print("100M:", end - start, len(enc))


def test_noencryptio():
    key = "123"
    buf = os.urandom(1024 * 1024 * 50)
    c = io.BytesIO(buf)
    enc = c.read()
    d = to_decryptio(io.BytesIO(enc), key)
    dec = d.read()
    assert buf == dec


def test_simpleencryptio():
    key = "123"
    buf = os.urandom(1024 * 1024 * 50)
    bio = io.BytesIO(buf)
    c = SimpleEncryptIO(bio, key, len(buf))
    assert total_len(c) == len(buf) + ENCRYPT_HEAD_LEN
    enc = c.read()
    d = to_decryptio(io.BytesIO(enc), key)
    assert total_len(d) == len(buf)
    dec = d.read()
    assert buf == dec


def test_chacha20encryptio():
    key = os.urandom(32)
    nonce = os.urandom(16)
    buf = os.urandom(1024 * 1024 * 50)
    bio = io.BytesIO(buf)
    c = ChaCha20EncryptIO(bio, key, nonce, len(buf))
    assert total_len(c) == len(buf) + ENCRYPT_HEAD_LEN
    enc = c.read()
    d = to_decryptio(io.BytesIO(enc), key)
    assert total_len(d) == len(buf)
    dec = d.read()
    assert buf == dec


def test_aes256cbcencryptio():
    key = os.urandom(32)
    iv = os.urandom(16)
    buf = os.urandom(1024 * 1024 * 50)
    bio = io.BytesIO(buf)
    c = AES256CBCEncryptIO(bio, key, iv, len(buf))

    assert total_len(c) == padding_size(len(buf), 16) + ENCRYPT_HEAD_LEN

    enc = c.read()
    print("enc", len(enc))
    d = to_decryptio(io.BytesIO(enc), key)
    # assert total_len(d) == len(buf)  # can be wrong
    dec = d.read()
    print("dec", len(dec))
    assert buf == dec


def test_aes256cbcencryptio_uniq():
    key = os.urandom(32)
    iv = os.urandom(16)
    buf = os.urandom(1024 * 1024 * 50)

    bio = io.BytesIO(buf)
    c = AES256CBCEncryptIO(bio, key, iv, len(buf))
    enc1 = c.read()

    bio = io.BytesIO(buf)
    c = AES256CBCEncryptIO(bio, key, iv, len(buf))
    enc2 = c.read()

    assert enc1 == enc2


def test_rapid_upload_params():
    key = os.urandom(32)
    nonce = os.urandom(16)
    buf = os.urandom(60 * constant.OneM)

    o = ChaCha20EncryptIO(io.BytesIO(buf), key, nonce, len(buf))
    enc0 = rapid_upload_params(o)

    o = EncryptType.ChaCha20.encrypt_io(io.BytesIO(buf), key, nonce)
    enc1 = rapid_upload_params(o)

    assert enc0 == enc1


def test_chunkio():
    f = io.BytesIO(b"0123")
    b = ChunkIO(f, 2)

    assert b.read() == b"01"
    assert b.tell() == 2

    b.seek(0)
    assert b.tell() == 0

    b = ChunkIO(f, 2)
    assert b.read() == b"01"
    assert b.tell() == 2

    b = ChunkIO(f, 2)
    assert b.read() == b"23"
    assert b.tell() == 2


def test_u64_u8x8():
    i = 2 ** 32
    b = u64_to_u8x8(i)
    x = u8x8_to_u64(b)
    assert i == x


def test_random_bytes():
    b1 = random_bytes(32, "abc")
    b2 = random_bytes(32, "abc")
    assert b1 == b2


def test_padding_size():
    i = 13
    bs = 16
    r = padding_size(i, bs)
    assert r == bs

    i = 16
    bs = 16
    r = padding_size(i, bs)
    assert r == bs

    i = 13
    bs = 16
    r = padding_size(i, bs, ceil=False)
    assert r == 0
