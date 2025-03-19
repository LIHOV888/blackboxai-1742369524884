document.addEventListener('DOMContentLoaded', () => {
    const urlInput = document.getElementById('urlInput');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const loadTemplateBtn = document.getElementById('loadTemplateBtn');
    const startDownloadBtn = document.getElementById('startDownloadBtn');
    const stopDownloadBtn = document.getElementById('stopDownloadBtn');
    const output = document.getElementById('output');

    let resources = [];

    function updateOutput(text) {
        output.textContent = text;
    }

    async function startScraping() {
        try {
            const url = urlInput.value.trim();
            if (!url) {
                updateOutput('Please enter a valid URL');
                return;
            }

            updateOutput('Starting scraping process...');
            startBtn.disabled = true;
            
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url })
            });

            const data = await response.json();
            
            if (data.error) {
                updateOutput(`Error: ${data.error}`);
            } else {
                resources = data.resources;
                updateOutput(`Found ${resources.length} resources\nScraping completed successfully`);
            }
        } catch (error) {
            updateOutput(`Error: ${error.message}`);
        } finally {
            startBtn.disabled = false;
        }
    }

    async function stopScraping() {
        try {
            const response = await fetch('/api/stop-scraping', {
                method: 'POST'
            });
            const data = await response.json();
            updateOutput(data.status);
        } catch (error) {
            updateOutput(`Error: ${error.message}`);
        }
    }

    async function startDownload() {
        if (!resources.length) {
            updateOutput('No resources to download. Please scrape first.');
            return;
        }

        try {
            updateOutput('Starting download...');
            startDownloadBtn.disabled = true;

            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ resources })
            });

            const data = await response.json();
            updateOutput(data.status);
        } catch (error) {
            updateOutput(`Error: ${error.message}`);
        } finally {
            startDownloadBtn.disabled = false;
        }
    }

    async function stopDownload() {
        try {
            const response = await fetch('/api/stop-download', {
                method: 'POST'
            });
            const data = await response.json();
            updateOutput(data.status);
        } catch (error) {
            updateOutput(`Error: ${error.message}`);
        }
    }

    async function loadTemplate() {
        try {
            updateOutput('Loading template...');
            loadTemplateBtn.disabled = true;

            const response = await fetch('/api/load-template', {
                method: 'POST'
            });

            const data = await response.json();
            if (data.url) {
                urlInput.value = data.url;
                updateOutput('Template loaded successfully');
            }
        } catch (error) {
            updateOutput(`Error: ${error.message}`);
        } finally {
            loadTemplateBtn.disabled = false;
        }
    }

    // Event listeners
    startBtn.addEventListener('click', startScraping);
    stopBtn.addEventListener('click', stopScraping);
    loadTemplateBtn.addEventListener('click', loadTemplate);
    startDownloadBtn.addEventListener('click', startDownload);
    stopDownloadBtn.addEventListener('click', stopDownload);

    // Poll status
    setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();
            
            if (status.status !== 'Ready' && status.status !== 'Complete') {
                let statusText = `Status: ${status.status}\n`;
                if (status.total > 0) {
                    statusText += `Progress: ${status.current}/${status.total}\n`;
                    statusText += `Speed: ${status.speed}`;
                }
                updateOutput(statusText);
            }
        } catch (error) {
            console.error('Error polling status:', error);
        }
    }, 1000);
});
