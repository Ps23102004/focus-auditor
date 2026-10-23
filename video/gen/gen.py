import json
CAPS=[(0.0,1.7,"Hi, I'm Parth Singh."),(2.0,5.3,"This is Focus Auditor, which I built on my own"),(5.3,8.9,"for the Amazon Build, Ship, Shape hackathon on Fire TV."),
(9.4,12.9,"Navigate with a remote, and blind users rely on a screen reader."),(13.7,18.2,"This button has no name, so a screen reader has nothing to say for it."),
(18.4,22.1,"My rules preview reads it as “unlabeled”."),(22.4,25.7,"I planted these bugs in Amazon's Hello World sample"),(25.7,29.1,"so I can show you the whole loop."),
(29.7,36.4,"There is also a trap. I planted three controls you can enter with the remote,"),(36.4,39.8,"but you can't leave with the D-pad. Only Back gets you out."),
(39.8,43.0,"One focus rule causes it,"),(43.0,46.5,"and it's easy to miss in code review."),(46.5,50.1,"Focus Auditor doesn't change the app. It drives the running app over adb"),
(50.1,53.5,"with real D-pad presses, 400 of them,"),(53.5,56.6,"and reads the accessibility tree at every step."),(56.9,60.3,"This is a replay of that recorded 11-minute run,"),
(60.3,65.5,"finding each with an exact key press that proves it."),(65.9,69.5,"The dashboard puts each finding on the real screenshot."),(69.5,73.2,"For icons, a local vision model"),
(73.4,76.9,"(Gemma 4) suggests a name. It runs on my laptop,"),(76.9,80.4,"never on the TV, and it's only a suggestion."),(80.7,86.2,"A person confirms it, and the test only checks that a name exists."),
(86.4,92.3,"Every finding becomes a frozen live test, and fails while the bug exists."),(92.6,95.8,"Then a coding agent fixes it in a sandboxed copy of the app,"),
(95.8,101.5,"and a gate refuses any changes outside the app's source files."),(101.8,107.1,"These unit tests attack that gate. Here the agent fixes one file."),
(107.1,110.5,"I rebuild and rerun the same four tests."),(110.5,115.9,"Four of four pass, and the icon now has a name."),(116.2,119.7,"The tests also fail if the app crashes, leaves,"),
(119.7,125.0,"or the control is simply deleted, so a fake fix can't pass."),(125.3,128.6,"I also tested the tester: about 1,100 offline tests,"),
(128.6,132.0,"600 random apps with known answers,"),(132.0,138.8,"and deliberate code breaks that the tests all catch."),
(138.8,145.6,"On four Google TV apps it had never seen, it found"),(145.6,149.1,"eight cards without a name. And when it can't be sure,"),(149.1,152.8,"it says inconclusive. Never pass."),
(152.8,156.2,"Amazon's Builder Tools teach agents how to build for"),(156.2,159.8,"Fire TV. Focus Auditor checks what they build."),(159.8,164.4,"I'm Parth Singh. It's open source under MIT. Thanks for watching.")]
caps="\n".join(f'<div class="cap clip" id="cap{i}" data-start="{s}" data-duration="{round(min(e-s+0.15,164.5-s),2)}"><span>{t}</span></div>' for i,(s,e,t) in enumerate(CAPS))
capjs="\n".join(f'tl.fromTo("#cap{i} span",{{y:14,opacity:0}},{{y:0,opacity:1,duration:0.22,ease:"power2.out"}},{s});' for i,(s,e,t) in enumerate(CAPS))
html=open("template.html").read().replace("%%CAPS%%",caps).replace("%%CAPJS%%",capjs)
open("../hf/index.html","w").write(html)
print(len(CAPS),"captions")
