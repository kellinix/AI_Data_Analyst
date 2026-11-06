# Apple verification roots

Public DER certificates downloaded from [Apple PKI](https://www.apple.com/certificateauthority/) on 6 November 2026.
The App Store Server Library validates the JWS certificate chain, bundle ID, environment and Apple app ID against these roots, with online certificate checks enabled.

| File | SHA-256 |
| --- | --- |
| AppleRootCA-G2.cer | c2b9b042dd57830e7d117dac55ac8ae19407d38e41d88f3215bc3a890444a050 |
| AppleRootCA-G3.cer | 63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179 |

These are public trust anchors, not private signing keys. Review changes against Apple's published certificates before replacing them.
