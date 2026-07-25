(function () {
  const micButton = document.getElementById("mic-button");
  const textArea = document.getElementById("command_text");
  const inputTypeField = document.getElementById("input_type");
  const statusEl = document.getElementById("voice-status");

  if (!micButton || !textArea) return;

  // Check if we are on a secure connection
  if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
    micButton.style.opacity = "0.4";
    micButton.title = "Voice input requires HTTPS";
    if (statusEl) {
      statusEl.textContent = "Voice input only works on a secure (https://) connection. You can still type your command.";
      statusEl.style.color = "#D9622B";
    }
    micButton.addEventListener("click", function () {
      alert("Voice input only works on a secure HTTPS connection.\n\nPlease access the site via your Render link (https://...) and use Chrome or Edge browser.");
    });
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    micButton.style.opacity = "0.4";
    micButton.title = "Not supported in this browser";
    if (statusEl) {
      statusEl.textContent = "Voice input is not supported in this browser. Please use Google Chrome or Microsoft Edge.";
      statusEl.style.color = "#D9622B";
    }
    micButton.addEventListener("click", function () {
      alert("Voice input is not supported in this browser.\n\nPlease open this site in Google Chrome or Microsoft Edge.");
    });
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
    // Ask for microphone permission explicitly
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(function () {
        try {
          recognition.start();
        } catch (e) {
          if (statusEl) statusEl.textContent = "Error starting microphone: " + e.message;
        }
      })
      .catch(function (err) {
        if (statusEl) {
          statusEl.textContent = "Microphone access denied. Click the lock icon in your browser address bar and set Microphone to Allow, then refresh.";
          statusEl.style.color = "#D9622B";
        }
      });
  });

  recognition.addEventListener("start", function () {
    listening = true;
    micButton.classList.add("listening");
    if (statusEl) {
      statusEl.textContent = "Listening... speak your invoice command now.";
      statusEl.style.color = "#9FC2AE";
    }
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
      statusEl.textContent = "Captured! Review the text below, then click Generate Invoice.";
      statusEl.style.color = "#9FC2AE";
    } else if (statusEl) {
      statusEl.textContent = "Didn't catch that — try again or type your command instead.";
      statusEl.style.color = "#D9622B";
    }
  });

  recognition.addEventListener("error", function (event) {
    listening = false;
    micButton.classList.remove("listening");
    let msg = "Microphone error: " + event.error;
    if (event.error === "not-allowed") {
      msg = "Microphone blocked. Click the lock icon in your address bar, set Microphone to Allow, then refresh the page.";
    } else if (event.error === "no-speech") {
      msg = "No speech detected. Try speaking louder or closer to the microphone.";
    } else if (event.error === "network") {
      msg = "Network error during voice recognition. Check your internet connection.";
    }
    if (statusEl) {
      statusEl.textContent = msg;
      statusEl.style.color = "#D9622B";
    }
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