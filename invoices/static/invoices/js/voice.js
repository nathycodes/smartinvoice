// voice.js — Browser-native speech-to-text using the Web Speech API.
// Falls back gracefully (hides mic button) on unsupported browsers.

(function () {
  const micButton = document.getElementById("mic-button");
  const textArea = document.getElementById("command_text");
  const inputTypeField = document.getElementById("input_type");
  const statusEl = document.getElementById("voice-status");

  if (!micButton || !textArea) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    micButton.style.display = "none";
    if (statusEl) {
      statusEl.textContent = "Voice input is not supported in this browser. You can still type your command.";
    }
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "en-NG";
  recognition.interimResults = true;
  recognition.continuous = false;

  let listening = false;

  micButton.addEventListener("click", function () {
    if (listening) {
      recognition.stop();
      return;
    }
    try {
      recognition.start();
    } catch (e) {
      console.error(e);
    }
  });

  recognition.addEventListener("start", function () {
    listening = true;
    micButton.classList.add("listening");
    if (statusEl) statusEl.textContent = "Listening... speak your invoice command now.";
    if (inputTypeField) inputTypeField.value = "VOICE";
  });

  recognition.addEventListener("result", function (event) {
    let finalTranscript = "";
    let interimTranscript = "";
    for (let i = 0; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        finalTranscript += transcript;
      } else {
        interimTranscript += transcript;
      }
    }
    textArea.value = (finalTranscript || interimTranscript).trim();
  });

  recognition.addEventListener("end", function () {
    listening = false;
    micButton.classList.remove("listening");
    if (statusEl && textArea.value.trim()) {
      statusEl.textContent = "Captured. Review the text below, then click \u201cGenerate Invoice.\u201d";
    } else if (statusEl) {
      statusEl.textContent = "Didn't catch that — try again or type your command.";
    }
  });

  recognition.addEventListener("error", function (event) {
    listening = false;
    micButton.classList.remove("listening");
    if (statusEl) statusEl.textContent = "Microphone error: " + event.error + ". You can type instead.";
  });

  // Example chips fill the textarea on click
  document.querySelectorAll(".example-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      textArea.value = chip.dataset.example;
      if (inputTypeField) inputTypeField.value = "TEXT";
      textArea.focus();
    });
  });
})();
