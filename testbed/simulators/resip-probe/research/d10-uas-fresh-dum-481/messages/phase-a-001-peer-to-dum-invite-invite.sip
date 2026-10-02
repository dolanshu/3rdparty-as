INVITE sip:uas@127.0.0.1:47771;transport=udp SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:47772;branch=z9hG4bK-invite-62cd7ef4763c4c14;rport
Max-Forwards: 70
From: <sip:caller@127.0.0.1:47772>;tag=caller-62cd7ef4763c4c14
To: <sip:uas@127.0.0.1:47771>
Call-ID: uas-restart-62cd7ef4763c4c14@127.0.0.1
CSeq: 1 INVITE
Contact: <sip:caller@127.0.0.1:47772;transport=udp>
Record-Route: <sip:127.0.0.1:47771;lr;transport=udp>
Content-Type: application/sdp
Content-Length: 159

v=0
o=- 4001 2 IN IP4 127.0.0.1
s=UAS restart negative recovery probe
c=IN IP4 127.0.0.1
t=0 0
m=audio 49170 RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=sendrecv
