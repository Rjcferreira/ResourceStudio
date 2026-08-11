"""Runtime Lua 5.4 para as primitivas do módulo Hardcode.

O texto é mantido separado do compilador para poder ser validado antes de
ser incorporado na VM. Não depende de bibliotecas externas do FiveM.
"""

LUA_CRYPTO_RUNTIME = r'''
local RS_CRYPTO = {}
local U32 = 0xffffffff
local function u32(x) return x & U32 end
local function rotr(x, n) return ((x >> n) | (x << (32 - n))) & U32 end
local function be4(s, p) local a,b,c,d=string.byte(s,p,p+3);return (((a*256+b)*256+c)*256+d)&U32 end
local function le4(s, p) local a,b,c,d=string.byte(s,p,p+3);return (a|(b<<8)|(c<<16)|(d<<24))&U32 end
local function putbe(x) return string.char((x>>24)&255,(x>>16)&255,(x>>8)&255,x&255) end
local function putle(x) return string.char(x&255,(x>>8)&255,(x>>16)&255,(x>>24)&255) end
local K={
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2}
function RS_CRYPTO.sha256(msg)
    local bitlen=#msg*8
    local pad=msg..string.char(128)
    while (#pad%64)~=56 do pad=pad..string.char(0) end
    local hi=math.floor(bitlen/4294967296);local lo=bitlen%4294967296
    pad=pad..putbe(hi)..putbe(lo)
    local h={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}
    for base=1,#pad,64 do
        local w={}
        for i=1,16 do w[i]=be4(pad,base+(i-1)*4) end
        for i=17,64 do local x=w[i-15];local y=w[i-2];local s0=rotr(x,7)~rotr(x,18)~(x>>3);local s1=rotr(y,17)~rotr(y,19)~(y>>10);w[i]=u32(w[i-16]+s0+w[i-7]+s1) end
        local a,b,c,d,e,f,g,z=table.unpack(h)
        for i=1,64 do local S1=rotr(e,6)~rotr(e,11)~rotr(e,25);local ch=(e&f)~((~e)&g);local t1=u32(z+S1+ch+K[i]+w[i]);local S0=rotr(a,2)~rotr(a,13)~rotr(a,22);local maj=(a&b)~(a&c)~(b&c);local t2=u32(S0+maj);z=g;g=f;f=e;e=u32(d+t1);d=c;c=b;b=a;a=u32(t1+t2) end
        h[1]=u32(h[1]+a);h[2]=u32(h[2]+b);h[3]=u32(h[3]+c);h[4]=u32(h[4]+d);h[5]=u32(h[5]+e);h[6]=u32(h[6]+f);h[7]=u32(h[7]+g);h[8]=u32(h[8]+z)
    end
    local out={};for i=1,8 do out[i]=putbe(h[i]) end;return table.concat(out)
end
function RS_CRYPTO.hmac(key,msg)
    if #key>64 then key=RS_CRYPTO.sha256(key) end
    key=key..string.rep(string.char(0),64-#key);local i={};local o={}
    for p=1,64 do local b=string.byte(key,p);i[p]=string.char(b~0x36);o[p]=string.char(b~0x5c) end
    return RS_CRYPTO.sha256(table.concat(o)..RS_CRYPTO.sha256(table.concat(i)..msg))
end
function RS_CRYPTO.hkdf(secret,salt,info,length)
    local prk=RS_CRYPTO.hmac(salt=='' and string.rep(string.char(0),32) or salt,secret);local out='';local prev='';local n=1
    while #out<length do prev=RS_CRYPTO.hmac(prk,prev..info..string.char(n));out=out..prev;n=n+1 end;return out:sub(1,length)
end
function RS_CRYPTO.equal(a,b)
    if #a~=#b then return false end
    local v=0;for i=1,#a do v=v|(string.byte(a,i)~string.byte(b,i)) end;return v==0
end
function RS_CRYPTO.open(secret,salt,nonce,ciphertext,tag)
    local material=RS_CRYPTO.hkdf(secret,salt,'ResourceStudio Hardcode v1',64)
    local encryption_key=material:sub(1,32);local mac_key=material:sub(33,64)
    local expected=RS_CRYPTO.hmac(mac_key,'RS-HC1'..salt..nonce..ciphertext)
    if not RS_CRYPTO.equal(expected,tag) then return nil,'tag de integridade inválida' end
    return RS_CRYPTO.chacha(encryption_key,nonce,ciphertext),nil
end
local function qr(x,a,b,c,d)
    x[a]=u32(x[a]+x[b]);x[d]=rotr(x[d]~x[a],16);x[c]=u32(x[c]+x[d]);x[b]=rotr(x[b]~x[c],20);x[a]=u32(x[a]+x[b]);x[d]=rotr(x[d]~x[a],24);x[c]=u32(x[c]+x[d]);x[b]=rotr(x[b]~x[c],25)
end
function RS_CRYPTO.chacha_block(key,counter,nonce)
    local x={0x61707865,0x3320646e,0x79622d32,0x6b206574};for p=1,32,4 do x[#x+1]=le4(key,p) end;x[13]=counter&U32;x[14]=le4(nonce,1);x[15]=le4(nonce,5);x[16]=le4(nonce,9);local o={table.unpack(x)}
    for _=1,10 do qr(x,1,5,9,13);qr(x,2,6,10,14);qr(x,3,7,11,15);qr(x,4,8,12,16);qr(x,1,6,11,16);qr(x,2,7,12,13);qr(x,3,8,9,14);qr(x,4,5,10,15) end
    local out={};for i=1,16 do out[i]=putle(u32(x[i]+o[i])) end;return table.concat(out)
end
function RS_CRYPTO.chacha(key,nonce,msg,counter)
    local out={};counter=counter or 1
    for p=1,#msg,64 do local block=RS_CRYPTO.chacha_block(key,counter,nonce);local n=math.min(64,#msg-p+1);local b={};for i=1,n do b[i]=string.char(string.byte(msg,p+i-1)~string.byte(block,i)) end;out[#out+1]=table.concat(b);counter=counter+1 end
    return table.concat(out)
end
return RS_CRYPTO
'''
