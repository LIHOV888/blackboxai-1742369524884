class FreepikScraperUI {
  constructor() {
    this.initializeElements();
    this.attachEventListeners();
    this.updateInterval = null;
  }

  initializeElements() {
    // Input and buttons
    this.urlInput = document.querySelector('input[type="text"]');
    this.startButton = document.querySelector("#startBtn");
    this.stopButton = document.querySelector("#stopBtn");
    this.loadTemplateButton = document.querySelector("#loadTemplateBtn");
    this.startDownloadButton = document.querySelector("#startDownloadBtn");
    this.stopDownloadButton = document.querySelector("#stopDownloadBtn");

    // Progress and status elements
    this.progressBar = document.querySelector(".progress-bar");
    this.logArea = document.querySelector(".font-mono");
    this.statusText = document.querySelector(".text-gray-600");
    this.downloadCount = document.querySelector(".text-gray-600:nth-child(2)");
    this.speedText = document.querySelector(".text-gray-600:nth-child(3)");
  }

  attachEventListeners() {
    // Scraping controls
    this.startButton.addEventListener("click", () => this.startScraping());
    this.stopButton.addEventListener("click", () => this.stopScraping());

    // Download controls
    this.startDownloadButton.addEventListener("click", () =>
      this.startDownload()
    );
    this.stopDownloadButton.addEventListener("click", () =>
      this.stopDownload()
    );

    // Template controls
    this.loadTemplateButton.addEventListener("click", () =>
      this.loadTemplate()
    );

    // URL input validation
    this.urlInput.addEventListener("input", () => this.validateUrl());
  }

  async startScraping() {
    const url = this.urlInput.value.trim();
    if (!url) {
      this.addLog("Error: Please enter a valid Freepik URL", "error");
      return;
    }

    this.setUIState("scraping");
    this.addLog("Starting scraping process...");

    try {
      const response = await fetch("/api/scrape", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) throw new Error("Scraping failed");

      const data = await response.json();
      this.addLog(`Found ${data.resources.length} resources`);
      this.resources = data.resources;

      this.setUIState("ready");
      this.addLog("Scraping completed successfully", "success");
    } catch (error) {
      this.addLog(`Error: ${error.message}`, "error");
      this.setUIState("error");
    }
  }

  async startDownload() {
    if (!this.resources?.length) {
      this.addLog("Error: No resources to download", "error");
      return;
    }

    this.setUIState("downloading");
    this.addLog("Starting download...");

    try {
      const response = await fetch("/api/download", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ resources: this.resources }),
      });

      if (!response.ok) throw new Error("Download failed");

      // Start progress polling
      this.startProgressPolling();
    } catch (error) {
      this.addLog(`Error: ${error.message}`, "error");
      this.setUIState("error");
    }
  }

  async loadTemplate() {
    try {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".json";

      input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (e) => {
          try {
            const template = JSON.parse(e.target.result);
            this.urlInput.value = template.url_pattern;
            this.addLog("Template loaded successfully", "success");
          } catch (error) {
            this.addLog("Error: Invalid template format", "error");
          }
        };
        reader.readAsText(file);
      };

      input.click();
    } catch (error) {
      this.addLog(`Error: ${error.message}`, "error");
    }
  }

  stopScraping() {
    fetch("/api/stop-scraping", { method: "POST" })
      .then(() => {
        this.setUIState("stopped");
        this.addLog("Scraping stopped");
      })
      .catch((error) => {
        this.addLog(`Error: ${error.message}`, "error");
      });
  }

  stopDownload() {
    fetch("/api/stop-download", { method: "POST" })
      .then(() => {
        this.setUIState("stopped");
        this.addLog("Download stopped");
        this.stopProgressPolling();
      })
      .catch((error) => {
        this.addLog(`Error: ${error.message}`, "error");
      });
  }

  startProgressPolling() {
    this.updateInterval = setInterval(async () => {
      try {
        const response = await fetch("/api/status");
        const status = await response.json();

        this.updateProgress(status);

        if (["Complete", "Stopped", "Error"].includes(status.status)) {
          this.stopProgressPolling();
          this.setUIState("ready");
        }
      } catch (error) {
        console.error("Error polling status:", error);
      }
    }, 1000);
  }

  stopProgressPolling() {
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
  }

  updateProgress(status) {
    // Update progress bar
    const progress = (status.current / status.total) * 100;
    this.progressBar.style.width = `${progress}%`;

    // Update status texts
    this.statusText.textContent = `Status: ${status.status}`;
    this.downloadCount.textContent = `Downloaded: ${status.current}/${status.total}`;
    this.speedText.textContent = `Speed: ${status.speed}`;
  }

  addLog(message, type = "info") {
    const div = document.createElement("div");
    div.textContent = message;

    switch (type) {
      case "error":
        div.className = "text-red-600";
        break;
      case "success":
        div.className = "text-emerald-600";
        break;
      default:
        div.className = "text-gray-600";
    }

    this.logArea.appendChild(div);
    this.logArea.scrollTop = this.logArea.scrollHeight;
  }

  setUIState(state) {
    const states = {
      ready: {
        startBtn: true,
        stopBtn: false,
        startDownloadBtn: true,
        stopDownloadBtn: false,
        urlInput: true,
      },
      scraping: {
        startBtn: false,
        stopBtn: true,
        startDownloadBtn: false,
        stopDownloadBtn: false,
        urlInput: false,
      },
      downloading: {
        startBtn: false,
        stopBtn: false,
        startDownloadBtn: false,
        stopDownloadBtn: true,
        urlInput: false,
      },
      stopped: {
        startBtn: true,
        stopBtn: false,
        startDownloadBtn: true,
        stopDownloadBtn: false,
        urlInput: true,
      },
      error: {
        startBtn: true,
        stopBtn: false,
        startDownloadBtn: false,
        stopDownloadBtn: false,
        urlInput: true,
      },
    };

    const currentState = states[state];
    if (!currentState) return;

    this.startButton.disabled = !currentState.startBtn;
    this.stopButton.disabled = !currentState.stopBtn;
    this.startDownloadButton.disabled = !currentState.startDownloadBtn;
    this.stopDownloadButton.disabled = !currentState.stopDownloadBtn;
    this.urlInput.disabled = !currentState.urlInput;

    // Add/remove disabled styling
    [
      this.startButton,
      this.stopButton,
      this.startDownloadButton,
      this.stopDownloadButton,
    ].forEach((button) => {
      button.classList.toggle("btn-disabled", button.disabled);
    });
  }

  validateUrl() {
    const url = this.urlInput.value.trim();
    const isValid = url.startsWith("https://www.freepik.com/");

    this.startButton.disabled = !isValid;
    this.startButton.classList.toggle("btn-disabled", !isValid);
    this.urlInput.classList.toggle("border-red-500", !isValid && url !== "");
  }
}

// Initialize the UI when the document is ready
document.addEventListener("DOMContentLoaded", () => {
  window.freepikUI = new FreepikScraperUI();
});
