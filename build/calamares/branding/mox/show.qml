import QtQuick 2.15
import calamares.slideshow 1.0

Presentation {
    id: presentation
    Rectangle { anchors.fill: parent; color: "#0b0b0f"; z: -1 }
    function nextSlide() { presentation.goToNextSlide() }
    Timer { interval: 7000; running: true; repeat: true; onTriggered: nextSlide() }
    function onActivate() { }
    function onLeave() { }

    Slide {
        Rectangle { anchors.fill: parent; color: "#0b0b0f"
            Column { anchors.centerIn: parent; spacing: 14
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "white"; font.pixelSize: 34; font.weight: Font.Light; text: "Setting up MOX" }
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#a7a7b2"; font.pixelSize: 16; text: "Sit back. This usually takes a few minutes." }
            }
        }
    }
    Slide {
        Rectangle { anchors.fill: parent; color: "#0b0b0f"
            Column { anchors.centerIn: parent; spacing: 14
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "white"; font.pixelSize: 34; font.weight: Font.Light; text: "Everything in one place" }
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#a7a7b2"; font.pixelSize: 16; text: "MOX Control looks after your hardware, AI, security and updates." }
            }
        }
    }
    Slide {
        Rectangle { anchors.fill: parent; color: "#0b0b0f"
            Column { anchors.centerIn: parent; spacing: 14
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "white"; font.pixelSize: 34; font.weight: Font.Light; text: "Almost there" }
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#a7a7b2"; font.pixelSize: 16; text: "Connect to the internet after your first start, and MOX finishes the rest." }
            }
        }
    }
}
