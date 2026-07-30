(function () {
  const micButton = document.getElementById("mic-button");
  const micIcon = micButton ? micButton.querySelector("i") : null;
  const textArea = document.getElementById("command_text");
  const inputTypeField = document.getElementById("input_type");
  const statusEl = document.getElementById("voice-status");

  if (!micButton || !textArea) return;

  const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
  const isLocalDevHost =
    localHosts.has(location.hostname) ||
    /^127(?:\.\d{1,3}){3}$/.test(location.hostname);

  // HTTPS check, but allow local development hosts.
  if (location.protocol !== "https:" && !isLocalDevHost) {
    micButton.style.opacity = "0.4";
    micButton.title = "Voice input requires HTTPS";

    if (statusEl) {
      statusEl.textContent =
        "Voice input only works on a secure (https://) connection. You can still type your command.";
      statusEl.style.color = "#D9622B";
    }

    micButton.addEventListener("click", function () {
      alert(
        "Voice input only works on a secure HTTPS connection.\n\nPlease access the site via your Render URL using Google Chrome or Microsoft Edge."
      );
    });

    return;
  }

  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    micButton.style.opacity = "0.4";
    micButton.title = "Browser not supported";

    if (statusEl) {
      statusEl.textContent =
        "Voice input is not supported in this browser. Please use Google Chrome or Microsoft Edge.";
      statusEl.style.color = "#D9622B";
    }

    micButton.addEventListener("click", function () {
      alert(
        "Voice input is not supported in this browser.\n\nPlease use Google Chrome or Microsoft Edge."
      );
    });

    return;
  }

  const recognition = new SpeechRecognition();

  console.log("Speech Recognition initialized.");

  recognition.lang = "en-US";
  recognition.interimResults = true;
  recognition.continuous = true;
  recognition.maxAlternatives = 1;

  let listening = false;
  let userRequestedStop = false;
  let audioContext = null;

  function playTone(frequency, durationMs, type) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;

      if (!audioContext) {
        audioContext = new AudioCtx();
      }

      if (audioContext.state === "suspended") {
        audioContext.resume();
      }

      const now = audioContext.currentTime;
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();

      oscillator.type = type || "sine";
      oscillator.frequency.setValueAtTime(frequency, now);

      gainNode.gain.setValueAtTime(0.0001, now);
      gainNode.gain.exponentialRampToValueAtTime(0.05, now + 0.02);
      gainNode.gain.exponentialRampToValueAtTime(0.0001, now + durationMs / 1000);

      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);

      oscillator.start(now);
      oscillator.stop(now + durationMs / 1000 + 0.03);
    } catch (error) {
      console.warn("Audio cue unavailable:", error);
    }
  }

  function setListeningUI(isListening) {
    if (!micButton || !micIcon) return;

    if (isListening) {
      micIcon.classList.remove("fa-microphone");
      micIcon.classList.add("fa-circle-stop");
      micButton.title = "Stop recording";
      micButton.setAttribute("aria-label", "Stop recording");
      micButton.classList.add("is-recording");
    } else {
      micIcon.classList.remove("fa-circle-stop");
      micIcon.classList.add("fa-microphone");
      micButton.title = "Speak your command";
      micButton.setAttribute("aria-label", "Speak your command");
      micButton.classList.remove("is-recording");
    }
  }

  function startSoundCue() {
    playTone(740, 120, "sine");
  }

  function stopSoundCue() {
    playTone(440, 140, "sine");
  }

  micButton.addEventListener("click", function () {
    console.log("Microphone button clicked.");

    if (listening) {
      userRequestedStop = true;
      recognition.stop();
      return;
    }

    userRequestedStop = false;
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then(function () {
        console.log("Microphone permission granted.");

        try {
          recognition.start();
        } catch (e) {
          console.error(e);

          if (statusEl) {
            statusEl.textContent =
              "Error starting microphone: " + e.message;
            statusEl.style.color = "#D9622B";
          }
        }
      })
      .catch(function (err) {
        console.error(err);

        if (statusEl) {
          statusEl.textContent =
            "Microphone access denied. Please allow microphone permission and refresh the page.";
          statusEl.style.color = "#D9622B";
        }
      });
  });

  recognition.addEventListener("start", function () {
    console.log("Speech recognition started.");

    listening = true;
    userRequestedStop = false;
    micButton.classList.add("listening");
    micButton.setAttribute("aria-pressed", "true");
    setListeningUI(true);
    startSoundCue();

    if (statusEl) {
      statusEl.textContent =
        "Listening... Speak your invoice command now.";
      statusEl.style.color = "#2E8B57";
    }

    if (inputTypeField) {
      inputTypeField.value = "VOICE";
    }
  });

  recognition.addEventListener("result", function (event) {
    let transcript = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }

    textArea.value = transcript.trim();

    console.log("Transcript:", transcript);
  });

  recognition.addEventListener("end", function () {
    console.log("Speech recognition ended.");

    if (!userRequestedStop && listening) {
      // Keep the mic active until the user explicitly clicks stop.
      setTimeout(function () {
        try {
          recognition.start();
        } catch (error) {
          console.warn("Unable to restart recognition:", error);
        }
      }, 150);
      return;
    }

    listening = false;
    micButton.classList.remove("listening");
    micButton.setAttribute("aria-pressed", "false");
    setListeningUI(false);
    stopSoundCue();

    if (!statusEl) return;

    if (textArea.value.trim()) {
      statusEl.textContent =
        "Captured! Review the text and click Generate Invoice.";
      statusEl.style.color = "#2E8B57";
    } else {
      statusEl.textContent =
        "No speech detected. Try again or type your command.";
      statusEl.style.color = "#D9622B";
    }
  });

  recognition.addEventListener("error", function (event) {
    console.error("SpeechRecognition Error:", event.error);

    listening = false;
    userRequestedStop = false;
    micButton.classList.remove("listening");
    micButton.setAttribute("aria-pressed", "false");
    setListeningUI(false);
    stopSoundCue();

    let msg = "Microphone error: " + event.error;

    switch (event.error) {
      case "not-allowed":
        msg =
          "Microphone permission denied. Please allow microphone access and refresh the page.";
        break;

      case "no-speech":
        msg =
          "No speech detected. Please speak clearly and try again.";
        break;

      case "audio-capture":
        msg =
          "No microphone detected. Please connect or enable a microphone.";
        break;

      case "network":
        msg =
          "Network error occurred during speech recognition.";
        break;

      case "aborted":
        msg =
          "Speech recognition was cancelled.";
        break;

      case "language-not-supported":
        msg =
          "Selected language is not supported.";
        break;
    }

    if (statusEl) {
      statusEl.textContent = msg;
      statusEl.style.color = "#D9622B";
    }
  });

  document.querySelectorAll(".example-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      textArea.value = chip.dataset.example;

      if (inputTypeField) {
        inputTypeField.value = "TEXT";
      }

      textArea.focus();
    });
  });
})();
