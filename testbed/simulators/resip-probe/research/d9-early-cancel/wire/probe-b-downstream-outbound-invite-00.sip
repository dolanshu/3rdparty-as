INVITE sip:+8613800138000@127.0.0.1:45676;transport=udp SIP/2.0
To: <sip:+8613800138000@127.0.0.1:45676;transport=udp>
Max-Forwards: 70
CSeq: 1 INVITE
From: <sip:as-sdp-roundtrip@127.0.0.1:45674>;tag=4323a47a
Call-ID: IbdgrwmQjfE-ZMr8TShLJA..
Contact: <sip:as-sdp-roundtrip@127.0.0.1:45674>
Via: SIP/2.0/UDP 127.0.0.1:45674;branch=z9hG4bK-524287-1---6860e9c75a787c50ccdbc0bdf;rport
Allow: INVITE, ACK, CANCEL, OPTIONS, BYE, UPDATE
Content-Type: application/sdp
Content-Length: 230

v=0
o=- 4101 4101 IN IP4 192.0.2.10
s=3rd-party AS POC call
c=IN IP4 192.0.2.10
t=0 0
m=audio 40000 RTP/AVP 0 8 101
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=rtpmap:101 telephone-event/8000
a=fmtp:101 0-15
a=sendrecv
