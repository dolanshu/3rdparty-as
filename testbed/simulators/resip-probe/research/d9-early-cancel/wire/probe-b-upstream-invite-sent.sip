INVITE sip:+8613800138000@127.0.0.1:45674 SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:45675;rport;branch=z9hG4bKf2108578683121bd892c5d5d99e686bf
Max-Forwards: 70
From: <sip:+86216180001@127.0.0.1>;tag=b609018f3db67e29442268935be4c876
To: <sip:+8613800138000@127.0.0.1>
Call-ID: 48f64baa94fdfcfdd79af4128905d375
CSeq: 1319846983 INVITE
Contact: <sip:+86216180001@127.0.0.1:45675>
Expires: 300
User-Agent: 3rd-party AS POC mock S-SBC
Route: <sip:127.0.0.1:47288;lr>
P-Asserted-Identity: <sip:+86216180001@ims.example.invalid>
P-charging-vector: icid-value=poc-office-to-mobile;icid-generated-at=ims.example.invalid
P-visited-network-id: ims.example.invalid
Privacy: none
Subject: office-to-mobile
Organization: office-to-mobile
Priority: normal
Feature-caps: *;+sip.608
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
