const puppeteer = require('puppeteer');
const express = require('express');
const cors = require('cors');
const app = express();

app.use(cors());
app.use(express.json());
app.use(express.static('static'));

let isScrapingActive = false;
let isDownloadingActive = false;
let status = {
    total: 0,
    current: 0,
    speed: '0 KB/s',
    status: 'Ready'
};

app.get('/', (req, res) => {
    res.sendFile(__dirname + '/static/index.html');
});

app.post('/api/scrape', async (req, res) => {
    const { url } = req.body;
    if (!url) {
        console.error('No URL provided');
        return res.status(400).json({ error: 'URL is required' });
    }

    if (!url.includes('freepik.com')) {
        console.error('Invalid URL provided:', url);
        return res.status(400).json({ error: 'Invalid Freepik URL' });
    }

    let browser;
    try {
        isScrapingActive = true;
        status.status = 'Initializing...';
        console.log(`Starting scraping from URL: ${url}`);

        browser = await puppeteer.launch({
            headless: 'new',
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        });

        const page = await browser.newPage();
        await page.setViewport({ width: 1920, height: 1080 });
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36');

        // Enable request interception
        await page.setRequestInterception(true);
        page.on('request', (request) => {
            if (['image', 'stylesheet', 'font'].includes(request.resourceType())) {
                request.abort();
            } else {
                request.continue();
            }
        });

        // Add console log listener
        page.on('console', msg => console.log('Browser console:', msg.text()));

        status.status = 'Loading page...';
        console.log('Navigating to URL:', url);
        await page.goto(url, { waitUntil: 'networkidle0', timeout: 30000 });

        status.status = 'Searching for content...';
        // Try different selectors for search results and profile pages
        const selectors = [
            '.list-content figure',          // Search results
            '.showcase__item',               // Profile items
            '.gallery-item',                 // Alternative items
            '.list-content__item',           // List items
            'article[data-type="image"]'     // Generic image articles
        ];

        console.log('Testing selectors...');
        let foundSelector = null;
        let itemCount = 0;

        for (const selector of selectors) {
            console.log(`Trying selector: ${selector}`);
            try {
                // Wait a short time for each selector
                await page.waitForSelector(selector, { timeout: 5000 });
                itemCount = await page.$$eval(selector, items => items.length);
                console.log(`Found ${itemCount} items with selector: ${selector}`);
                if (itemCount > 0) {
                    foundSelector = selector;
                    break;
                }
            } catch (error) {
                console.log(`Selector ${selector} not found:`, error.message);
            }
        }

        if (!foundSelector) {
            throw new Error('Could not find any content on the page');
        }

        status.status = 'Extracting resources...';
        console.log(`Using selector: ${foundSelector}`);

        // Extract resources
        const resources = await page.evaluate((selector) => {
            const items = document.querySelectorAll(selector);
            console.log(`Processing ${items.length} items...`);
            
            return Array.from(items).map((item, index) => {
                // Try multiple ways to find links and titles
                const link = item.querySelector('a') || item.closest('a');
                const title = item.querySelector('.title, figcaption, .caption, .description, img[alt]');
                const img = item.querySelector('img');
                
                const resource = {
                    url: link ? link.href : '',
                    title: title ? title.textContent.trim() : (img ? img.alt : `Resource ${index + 1}`),
                    preview_url: img ? (img.dataset.src || img.src) : '',
                    type: 'resource'
                };
                
                console.log(`Extracted item ${index + 1}:`, resource);
                return resource;
            });
        }, foundSelector);

        if (!resources.length) {
            throw new Error('No resources could be extracted');
        }

        // Filter out invalid resources
        const validResources = resources.filter(r => r.url && r.url.includes('freepik.com'));
        if (!validResources.length) {
            throw new Error('No valid Freepik resources found');
        }

        await browser.close();
        browser = null;
        isScrapingActive = false;
        status.total = validResources.length;
        status.status = 'Complete';
        console.log(`Successfully extracted ${validResources.length} resources`);

        res.json({
            resources: validResources,
            total: validResources.length,
            message: `Found ${validResources.length} resources`
        });
    } catch (error) {
        isScrapingActive = false;
        status.status = `Error: ${error.message}`;
        console.error('Scraping failed:', error);
        res.status(500).json({ 
            error: error.message,
            details: error.stack
        });
    } finally {
        if (browser) {
            await browser.close().catch(console.error);
        }
    }
});

app.post('/api/download', async (req, res) => {
    const { resources } = req.body;
    if (!resources || !resources.length) {
        return res.status(400).json({ error: 'No resources provided' });
    }

    isDownloadingActive = true;
    status.status = 'Downloading';
    status.total = resources.length;
    status.current = 0;

    res.json({ status: 'Download started' });
});

app.post('/api/stop-scraping', (req, res) => {
    isScrapingActive = false;
    status.status = 'Stopped';
    res.json({ status: 'Scraping stopped' });
});

app.post('/api/stop-download', (req, res) => {
    isDownloadingActive = false;
    status.status = 'Stopped';
    res.json({ status: 'Download stopped' });
});

app.get('/api/status', (req, res) => {
    res.json(status);
});

const port = 8000;
app.listen(port, () => {
    console.log(`Server running at http://localhost:${port}`);
});