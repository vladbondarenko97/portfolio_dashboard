const API_BASE = "http://pc.vlad.yt:8080";

// 1. HELPER: Format Date to "MMM DD, YYYY"
function formatDate(dateStr) {
    const date = new Date(dateStr + "T12:00:00"); 
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// 2. HELPER: Convert large numbers to Millions/Thousands
function formatCompact(valStr) {
    const num = parseFloat(valStr.replace(/[$,]/g, ''));
    if (num >= 1000000) return (num / 1000000).toFixed(2) + "M";
    if (num >= 1000) return (num / 1000).toFixed(1) + "K";
    return num.toFixed(2);
}

// 3. MAIN TERMINAL LOGGER
function log(content, type = 'info') {
    const consoleLog = document.getElementById('consoleLog');
    const time = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    const entry = document.createElement('div');
    entry.className = "mb-4 border-l-2 border-zinc-800 pl-4";
    
    let color = "text-zinc-500";
    if (type === 'success') color = "text-green-500 font-bold";
    if (type === 'error') color = "text-red-500 font-bold";
    if (type === 'cmd') color = "text-blue-400";
    
    entry.innerHTML = `<div class="text-[9px] mb-1"><span class="text-zinc-700">[${time}]</span> <span class="${color} uppercase">${type}</span></div>`;

    // CHECK: Is this the Whale Hunt XML?
    if (typeof content === 'string' && content.includes('<whale_hunt')) {
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(content, "text/xml");
        const contracts = Array.from(xmlDoc.getElementsByTagName("contract"));
        
        // Calculate Totals for Summary
        let bullPrem = 0; let bearPrem = 0;
        contracts.forEach(c => {
            const p = parseFloat(c.getAttribute('premium_spent').replace(/[$,]/g, ''));
            if (c.getAttribute('type') === 'CALL') bullPrem += p; else bearPrem += p;
        });

        // Sort by premium (Highest first)
        contracts.sort((a, b) => {
            const premA = parseFloat(a.getAttribute('premium_spent').replace(/[$,]/g, ''));
            const premB = parseFloat(b.getAttribute('premium_spent').replace(/[$,]/g, ''));
            return premB - premA;
        });

        // Build Pretty Summary Header
        let summaryHtml = `
            <div class="flex gap-4 mb-4 bg-zinc-900/40 p-3 rounded border border-zinc-800">
                <div><span class="text-zinc-500 text-[10px] block uppercase">Call Premium</span><span class="text-green-500 font-bold">$${(bullPrem/1e6).toFixed(2)}M</span></div>
                <div class="border-r border-zinc-800"></div>
                <div><span class="text-zinc-500 text-[10px] block uppercase">Put Premium</span><span class="text-red-500 font-bold">$${(bearPrem/1e6).toFixed(2)}M</span></div>
                <div class="ml-auto text-right"><span class="text-zinc-500 text-[10px] block uppercase">Sentiment</span><span class="${bullPrem > bearPrem ? 'text-green-400' : 'text-red-400'} font-bold">${bullPrem > bearPrem ? 'BULLISH' : 'BEARISH'}</span></div>
            </div>
            <div class="grid grid-cols-1 gap-2">`;
        
        contracts.forEach(c => {
            const type = c.getAttribute('type');
            const accent = type === 'CALL' ? 'text-green-400' : 'text-red-400';
            const premRaw = c.getAttribute('premium_spent');
            
            summaryHtml += `
                <div class="bg-zinc-950 border border-zinc-900 p-3 rounded hover:bg-zinc-900 transition-all group">
                    <div class="flex justify-between items-start">
                        <div class="text-[12px]">
                            <span class="${accent} font-bold">${type === 'CALL' ? '🔥' : '🩸'} ${type}:</span>
                            <span class="text-white ml-1 font-bold">${formatDate(c.getAttribute('expiration'))}</span>
                            <span class="text-zinc-500 mx-1">/</span>
                            <span class="text-zinc-200">$${c.getAttribute('strike')} Strike</span>
                            <span class="text-zinc-600 mx-2">—</span>
                            <span class="text-white font-bold">$${formatCompact(premRaw)} premium</span>
                        </div>
                    </div>
                    
                    <div class="grid grid-cols-4 gap-2 mt-3 pt-2 border-t border-zinc-900 text-[9px] group-hover:border-zinc-700">
                        <div><span class="text-zinc-600 block uppercase">Intensity</span><span class="text-blue-400">${c.getAttribute('vol_oi_ratio')}</span></div>
                        <div><span class="text-zinc-600 block uppercase">Vol/OI</span><span class="text-zinc-400">${c.getAttribute('volume')} / ${c.getAttribute('open_interest')}</span></div>
                        <div><span class="text-zinc-600 block uppercase">Expectation</span><span class="text-orange-400">${c.getAttribute('implied_volatility')} IV</span></div>
                        <div><span class="text-zinc-600 block uppercase">Slippage</span><span class="text-zinc-500">${c.getAttribute('spread')} Spread</span></div>
                    </div>
                </div>`;
        });
        
        summaryHtml += `</div>`;
        entry.innerHTML += summaryHtml;
    }
    // CHECK: Is this the Physical Arbitrage XML?
    else if (typeof content === 'string' && content.includes('<physical_arbitrage')) {
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(content, "text/xml");
        const root = xmlDoc.getElementsByTagName("physical_arbitrage")[0];
        const listings = Array.from(xmlDoc.getElementsByTagName("listing"));

        if (!root || listings.length === 0) {
            entry.innerHTML += `<div class="text-red-500">Scan failed or returned no retail inventory.</div>`;
            consoleLog.appendChild(entry);
            consoleLog.scrollTop = consoleLog.scrollHeight;
            return;
        }

        const comexSpot = root.getAttribute("comex_spot");
        const timestamp = root.getAttribute("timestamp");

        // Build Pretty Summary Header for Arbitrage
        let summaryHtml = `
            <div class="flex gap-4 mb-4 bg-zinc-900/40 p-3 rounded border border-zinc-800">
                <div><span class="text-zinc-500 text-[10px] block uppercase">COMEX Spot</span><span class="text-blue-400 font-bold">${comexSpot}</span></div>
                <div class="border-r border-zinc-800"></div>
                <div><span class="text-zinc-500 text-[10px] block uppercase">Dealers Scanned</span><span class="text-white font-bold">${listings.length}</span></div>
                <div class="ml-auto text-right"><span class="text-zinc-500 text-[10px] block uppercase">Engine Timestamp</span><span class="text-zinc-400 font-bold">${timestamp.split(' ')[1]}</span></div>
            </div>
            <div class="grid grid-cols-1 gap-2">`;
        
        listings.forEach(l => {
            const itemId = l.getAttribute("item_id");
            const name = l.getAttribute("name");
            const totalCost = l.getAttribute("total_cost");
            const shipping = l.getAttribute("shipping");
            const premDollars = l.getAttribute("premium_dollars");
            const premPercent = l.getAttribute("premium_percent");
            const status = l.getAttribute("status");
            
            // Format Status Colors
            let statusColor = "text-zinc-500";
            if (status.includes("InStock")) statusColor = "text-green-500 font-bold";
            else if (status.includes("Fallback")) statusColor = "text-yellow-500";

            // CHANGED: Wrapped the card in an <a> tag pointing to the eBay listing
            summaryHtml += `
                <a href="https://www.ebay.com/itm/${itemId}" target="_blank" class="block bg-zinc-950 border border-zinc-900 p-3 rounded hover:border-blue-900 transition-all group cursor-pointer text-left">
                    <div class="flex justify-between items-start">
                        <div class="text-[12px] truncate w-3/4 pr-4">
                            <span class="text-blue-400 font-bold">🪙 RETAIL:</span>
                            <span class="text-zinc-200 ml-1 group-hover:text-blue-400 transition-colors" title="${name}">${name}</span>
                        </div>
                        <div class="text-right w-1/4">
                            <div class="text-white font-bold tracking-tighter group-hover:text-blue-400 transition-colors">${totalCost}</div>
                            <div class="text-[9px] text-zinc-600 uppercase">Total Cost</div>
                        </div>
                    </div>
                    
                    <div class="grid grid-cols-4 gap-2 mt-3 pt-2 border-t border-zinc-900 text-[9px] group-hover:border-blue-900/50">
                        <div><span class="text-zinc-600 block uppercase">Premium %</span><span class="text-orange-400 font-bold">+${premPercent}</span></div>
                        <div><span class="text-zinc-600 block uppercase">Premium $</span><span class="text-orange-400">+${premDollars}</span></div>
                        <div><span class="text-zinc-600 block uppercase">Shipping</span><span class="text-zinc-400">${shipping}</span></div>
                        <div><span class="text-zinc-600 block uppercase">Status</span><span class="${statusColor}">${status}</span></div>
                    </div>
                </a>`;
        });
        
        summaryHtml += `</div>`;
        entry.innerHTML += summaryHtml;
    } 
    else {
        // Fallback for standard text/error logs
        entry.innerHTML += `<div class="text-zinc-300 whitespace-pre-wrap">${content}</div>`;
    }

    consoleLog.appendChild(entry);
    consoleLog.scrollTop = consoleLog.scrollHeight;
}

// Function to handle physical arbitrage scans
async function triggerPhysicalArbScan() {
    log(`Initializing Physical Arbitrage Engine (Silver Eagles)...`, 'cmd');
    try {
        const res = await fetch(`${API_BASE}/api/silver_eagle_prices`);
        const contentType = res.headers.get("content-type");
        
        if (contentType && contentType.includes("application/xml")) {
             const xmlText = await res.text();
             log(xmlText, 'success'); 
        } else {
             const text = await res.text();
             log(`Error fetching data: ${text}`, 'error');
        }
    } catch (e) { log(`System Error: ${e.message}`, 'error'); }
}

// Logic to run standard morning/evening hunts
async function runPredefined(mode) {
    log(`Broadcasting ${mode.toUpperCase()} position hunt...`, 'cmd');
    const ticker = document.getElementById('scanTicker').value || "SPY";
    try {
        const res = await fetch(`${API_BASE}/api/${mode}?ticker=${ticker}`);
        const result = await res.json();
        if (result.status === "success") log(result.data, 'success');
        else log(result.message, 'error');
    } catch (e) { log(e.message, 'error'); }
}

// Logic to run the Custom XML-based scan
async function runCustomScan() {
    const ticker = document.getElementById('scanTicker').value || "AMD";
    const vol = document.getElementById('scanVol').value;
    const dte = document.getElementById('scanDTE').value;
    const premium = document.getElementById('scanPremium').value;
    
    log(`Initiating Custom Whale Scan for $${ticker.toUpperCase()}...`, 'cmd');
    
    try {
        const url = `${API_BASE}/api/custom?ticker=${ticker}&min_vol_oi=${vol}&min_premium=${premium}&max_dte=${dte}`;
        const res = await fetch(url);
        const contentType = res.headers.get("content-type");

        if (contentType && contentType.includes("application/xml")) {
            const xmlText = await res.text();
            // CRITICAL FIX: Pass xmlText directly, DO NOT escape it here
            log(xmlText, 'success'); 
        } else {
            const result = await res.json();
            log(result.data || result.message, result.status === 'success' ? 'success' : 'error');
        }
    } catch (e) { log(`Network Error: ${e.message}`, 'error'); }
}

// Function to handle physical arbitrage scans (placeholder for future use)
async function triggerPhysicalArbScan() {
    log(`Initializing Physical Arbitrage Engine...`, 'cmd');
    try {
        const res = await fetch(`${API_BASE}/api/silver_eagle_prices`);
        const contentType = res.headers.get("content-type");
        
        if (contentType && contentType.includes("application/xml")) {
             const xmlText = await res.text();
             log(xmlText, 'success'); // Requires adding an XML parser specifically for the arb data in the log function
        } else {
            log("Error fetching physical arbitrage data.", 'error');
        }
    } catch (e) { log(e.message, 'error'); }
}

// Status checker
async function checkStatus() {
    try {
        const res = await fetch(`${API_BASE}/help`);
        if (res.ok) {
            document.getElementById('apiStatus').innerText = "ONLINE";
            document.getElementById('apiStatus').className = "text-green-500";
            document.getElementById('statusDot').className = "w-2 h-2 bg-green-500 rounded-full status-pulse";
        }
    } catch (e) {
        document.getElementById('apiStatus').innerText = "OFFLINE (CHECK PC.VLAD.YT)";
        document.getElementById('apiStatus').className = "text-red-500";
        document.getElementById('statusDot').className = "w-2 h-2 bg-red-500 rounded-full";
    }
}

// ==========================================
// --- 4. WAR ROOM: SCENARIO ENGINE ---
// ==========================================

let warRoomDebounceTimer;
let currentBaseData = null; // Stores the live environment from the API

// Draws a mathematical Bell Curve with a glowing tail-risk dot
function drawBellCurve(hypoVmri) {
    const canvas = document.getElementById('bellCurve');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    // FIX: Match internal resolution to display size (Removes Blurriness)
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // Draw the baseline curve
    ctx.beginPath();
    ctx.strokeStyle = '#3f3f46'; 
    ctx.lineWidth = panel3.classList.contains('fullscreen-mode') ? 4 : 2; // Thicker lines in full screen
    
    const mean = w * 0.4; 
    const stdDev = w * 0.15;

    for(let i=0; i<=w; i++) {
        const x = i;
        const y = h - (h * 0.8) * Math.exp(-Math.pow(x - mean, 2) / (2 * Math.pow(stdDev, 2)));
        if (i===0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Dot logic
    let dotX = ((hypoVmri - 100) / 250) * w;
    if (dotX < 10) dotX = 10;
    if (dotX > w - 10) dotX = w - 10;
    const dotY = h - (h * 0.8) * Math.exp(-Math.pow(dotX - mean, 2) / (2 * Math.pow(stdDev, 2)));

    let color = '#22c55e';
    if (hypoVmri >= 150) color = '#eab308';
    if (hypoVmri >= 250) color = '#ef4444';

    // Draw High-Res Dot
    ctx.beginPath();
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    // Larger dot and glow in full screen
    const dotSize = panel3.classList.contains('fullscreen-mode') ? 10 : 4;
    ctx.shadowBlur = panel3.classList.contains('fullscreen-mode') ? 20 : 8;
    ctx.arc(dotX, dotY, dotSize, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
}

// Generates the Goldman-style impact text
function generateDeltaAnalysis(hypo) {
    const el = document.getElementById('deltaAnalysis');
    let text = "";

    if (hypo.vmri >= 300) {
        text = `CRITICAL: Systemic liquidity freezing. Expected Silver physical premiums to gap >35%. High-yield credit markets seizing. Portfolio margin calls highly probable.`;
        el.className = "text-[8px] text-red-400 mt-1 leading-tight border-t border-zinc-800 pt-1 font-mono";
    } else if (hypo.vmri >= 250) {
        text = `WARNING: Extreme volatility premium expansion. Options pricing +40%. Physical metals catching aggressive bids on credit stress. Deploy hedge triggers.`;
        el.className = "text-[8px] text-red-400 mt-1 leading-tight border-t border-zinc-800 pt-1 font-mono";
    } else if (hypo.vmri >= 150) {
        text = `NOMINAL: Standard risk parameters active. Equity/Bond correlations tracking normally. Theta decay optimal for neutral premium selling.`;
        el.className = "text-[8px] text-yellow-400 mt-1 leading-tight border-t border-zinc-800 pt-1 font-mono";
    } else {
        text = `COMPLACENT: Volatility severely suppressed. Gamma squeeze danger elevated. Unfavorable risk/reward for long options. Physical premiums compressing.`;
        el.className = "text-[8px] text-green-400 mt-1 leading-tight border-t border-zinc-800 pt-1 font-mono";
    }

    if (hypo.tnx > 5.0 && hypo.dxy > 105) {
        text += ` Heavy pressure on risk-assets from Dollar/Yield wrecking ball.`;
    }
    el.innerText = text;
}

// Updates the text numbers next to the sliders to show Base + Shift
function updateSliderLabels() {
    const dxyShift = parseFloat(document.getElementById('shiftDxy').value);
    const tnxShift = parseFloat(document.getElementById('shiftTnx').value);
    const oasShift = parseFloat(document.getElementById('shiftOas').value);
    const vixShift = parseFloat(document.getElementById('shiftVix').value);

    if (currentBaseData) {
        document.getElementById('baseDxyTxt').innerText = `(${currentBaseData.dxy.toFixed(2)})`;
        document.getElementById('valDxy').innerText = `${(currentBaseData.dxy + dxyShift).toFixed(2)} [${dxyShift > 0 ? '+' : ''}${dxyShift.toFixed(2)}]`;
        
        document.getElementById('baseTnxTxt').innerText = `(${currentBaseData.tnx.toFixed(2)}%)`;
        document.getElementById('valTnx').innerText = `${(currentBaseData.tnx + tnxShift).toFixed(2)}% [${tnxShift > 0 ? '+' : ''}${tnxShift.toFixed(2)}%]`;
        
        document.getElementById('baseOasTxt').innerText = `(${currentBaseData.oas.toFixed(2)})`;
        document.getElementById('valOas').innerText = `${(currentBaseData.oas + oasShift).toFixed(2)} [${oasShift > 0 ? '+' : ''}${oasShift.toFixed(2)}]`;
        
        document.getElementById('baseVixTxt').innerText = `(${currentBaseData.vix.toFixed(2)})`;
        document.getElementById('valVix').innerText = `${(currentBaseData.vix * (1 + (vixShift/100))).toFixed(2)} [${vixShift > 0 ? '+' : ''}${vixShift}%]`;
    } else {
        document.getElementById('valDxy').innerText = (dxyShift > 0 ? '+' : '') + dxyShift.toFixed(2);
        document.getElementById('valTnx').innerText = (tnxShift > 0 ? '+' : '') + tnxShift.toFixed(2) + '%';
        document.getElementById('valOas').innerText = (oasShift > 0 ? '+' : '') + oasShift.toFixed(2);
        document.getElementById('valVix').innerText = (vixShift > 0 ? '+' : '') + vixShift.toFixed(0) + '%';
    }
}

// ==========================================
// --- PANEL ZOOM ENGINE ---
// ==========================================

function zoomPanel(panelId, delta) {
    const panel = document.getElementById(panelId);
    const content = panel.querySelector('.zoomable');
    if (!content) return;

    // 1. Get current zoom
    let oldZoom = parseFloat(localStorage.getItem(`vladhq_zoom_${panelId}`) || 1.0);
    
    // 2. Calculate target zoom and fix Javascript's floating point math bug (e.g. 0.900000001)
    let newZoom = oldZoom + delta;
    newZoom = Math.round(newZoom * 100) / 100;
    
    // 3. --- THE ZOOM GUARDRAILS ---
    if (newZoom < 0.8) newZoom = 0.8; 
    if (newZoom > 1.25) newZoom = 1.25; 

    // 4. ABORT IF AT LIMIT: If the math says we didn't actually change anything, stop here!
    if (newZoom === oldZoom) {
        return; // Exits the function completely. No refresh, no flickering.
    }

    // 5. If we made it here, it's a valid new zoom. Save and apply.
    localStorage.setItem(`vladhq_zoom_${panelId}`, newZoom);
    applyZoom(panelId, newZoom);
    
    // 6. Refresh targets
    const iframe = panel.querySelector('iframe');
    if (iframe) {
        iframe.src += ''; 
    }
    
    if(panelId === 'panel3' && typeof drawBellCurve === 'function') {
         setTimeout(() => drawBellCurve(parseFloat(document.getElementById('warVmriScore').innerText || 0)), 50);
    }
}

function applyZoom(panelId, zoomLevel) {
    const panel = document.getElementById(panelId);
    if (!panel) return;
    
    const content = panel.querySelector('.zoomable');
    if (!content) return;

    const inverseScale = (1 / zoomLevel) * 100;

    // --- IFRAME SPECIFIC LOGIC ---
    if (content.tagName.toLowerCase() === 'iframe') {
        // Clear any buggy CSS transforms
        content.style.transform = 'none';
        
        // Use native hardware zoom. This forces the internal Chart.js canvas 
        // to re-render at the new viewport size, eliminating empty space.
        content.style.zoom = zoomLevel;
        
        // Expand the bounding box so it stays anchored to the panel edges
        content.style.width = `${inverseScale}%`;
        content.style.height = `${inverseScale}%`;
        
    } 
    // --- NATIVE HTML DIV LOGIC ---
    else {
        content.style.transform = `scale(${zoomLevel})`;
        content.style.transformOrigin = 'top left';
        content.style.width = `${inverseScale}%`;
        
        // Only force height expansion if zooming OUT to prevent clipping
        if (zoomLevel < 1.0) {
            content.style.height = `${inverseScale}%`;
        } else {
            content.style.height = `100%`;
        }
    }
}

// ==========================================
// --- 5. DRAG & DROP / MODAL ENGINE ---
// ==========================================


let draggedPanel = null;

function toggleFullscreen(panelId) {
    const panel = document.getElementById(panelId);
    const backdrop = document.getElementById('modalBackdrop');
    const btn = panel.querySelector('.btn-maximize');
    const content = panel.querySelector('.zoomable');
    
    if (panel.classList.contains('fullscreen-mode')) {
        // --- MINIMIZE LOGIC ---
        panel.classList.remove('fullscreen-mode');
        backdrop.classList.add('hidden');
        btn.innerText = '[MAX]';
        panel.setAttribute('draggable', 'true');
        
        // Restore the user's custom zoom level
        let savedZoom = parseFloat(localStorage.getItem(`vladhq_zoom_${panelId}`) || 1.0);
        applyZoom(panelId, savedZoom);
        
    } else {
        // --- MAXIMIZE LOGIC ---
        panel.classList.add('fullscreen-mode');
        backdrop.classList.remove('hidden');
        btn.innerText = '[MIN]';
        panel.setAttribute('draggable', 'false');
        
        // Temporarily reset zoom to 1.0 so the chart fills the whole screen naturally
        if (content) {
            content.style.transform = 'none';
            content.style.zoom = 1.0;
            content.style.width = '100%';
            content.style.height = '100%';
        }
    }

    // Force redraws
    if (panelId === 'panel3') {
        setTimeout(() => {
            updateSliderLabels(); 
            drawBellCurve(parseFloat(document.getElementById('warVmriScore').innerText || 0));
        }, 50);
    }
}


document.addEventListener('DOMContentLoaded', () => {
    const panels = document.querySelectorAll('.draggable-panel');

    // Load Default Panels
    setTimeout(() => fetchDarkPoolProfile('SPY'), 1500); 
    setTimeout(() => loadDealerMap(), 1600); // <--- Add this line

    // Add this to your DOMContentLoaded in app.js
    document.getElementById('modalBackdrop').addEventListener('click', () => {
        // Find whichever panel is currently in fullscreen mode and shrink it
        const activePanel = document.querySelector('.fullscreen-mode');
        if (activePanel) toggleFullscreen(activePanel.id);
    });
    
    panels.forEach(panel => {
        // When drag starts, apply styling
        panel.addEventListener('dragstart', function(e) {
            draggedPanel = this;
            setTimeout(() => this.classList.add('panel-dragging'), 0);
        });

        // When drag ends, remove styling
        panel.addEventListener('dragend', function() {
            setTimeout(() => this.classList.remove('panel-dragging'), 0);
            draggedPanel = null;
        });

        // Prevent default to allow dropping
        panel.addEventListener('dragover', function(e) {
            e.preventDefault(); 
        });

        // Handle the Drop (Swap the physical HTML nodes in the DOM)
        panel.addEventListener('drop', function(e) {
            e.preventDefault();
            if (this !== draggedPanel && draggedPanel !== null) {
                let allPanels = [...document.querySelectorAll('.draggable-panel')];
                let draggedIndex = allPanels.indexOf(draggedPanel);
                let targetIndex = allPanels.indexOf(this);
                
                // CSS Grid respects DOM order, so we literally move the element
                if (draggedIndex < targetIndex) {
                    this.parentNode.insertBefore(draggedPanel, this.nextSibling);
                } else {
                    this.parentNode.insertBefore(draggedPanel, this);
                }
            }
        });
    });

    // SAFETY CATCH: Prevent War Room Sliders from triggering the Panel Drag
    document.querySelectorAll('input[type="range"], button, canvas').forEach(el => {
        el.addEventListener('mousedown', (e) => {
            const panel = e.target.closest('.draggable-panel');
            if(panel && !panel.classList.contains('fullscreen-mode')) panel.setAttribute('draggable', 'false');
        });
        el.addEventListener('mouseup', (e) => {
            const panel = e.target.closest('.draggable-panel');
            if(panel && !panel.classList.contains('fullscreen-mode')) panel.setAttribute('draggable', 'true');
        });
        el.addEventListener('mouseleave', (e) => {
            const panel = e.target.closest('.draggable-panel');
            if(panel && !panel.classList.contains('fullscreen-mode')) panel.setAttribute('draggable', 'true');
        });
    });
});

// Fires the API request and updates the UI Visuals
async function updateWarRoom() {
    const statusEl = document.getElementById('warStatus');
    statusEl.innerText = "CALCULATING...";
    statusEl.className = "text-blue-400 font-bold";

    const payload = {
        dxy_shift: parseFloat(document.getElementById('shiftDxy').value),
        tnx_shift: parseFloat(document.getElementById('shiftTnx').value),
        oas_shift: parseFloat(document.getElementById('shiftOas').value),
        vix_shift_pct: parseFloat(document.getElementById('shiftVix').value)
    };

    try {
        const res = await fetch(`${API_BASE}/api/war_room`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.status === 'success') {
            currentBaseData = data.current; // Store base environment
            updateSliderLabels(); // Re-render text with accurate math
            
            const hypoVmri = data.hypothetical.vmri;
            
            // 1. Update the Text Score
            const scoreDisplay = document.getElementById('warVmriScore');
            scoreDisplay.innerText = hypoVmri.toFixed(1);
            
            // 2. Animate the Tripwire Gauge
            const fill = document.getElementById('tripwireFill');
            let heightPct = (hypoVmri / 350) * 100;
            if (heightPct > 100) heightPct = 100; 
            fill.style.height = `${heightPct}%`;

            // 3. Update Colors based on Risk Tier
            fill.classList.remove('warning', 'danger');
            scoreDisplay.className = "text-[10px] font-bold mt-2"; 

            if (hypoVmri >= 250) {
                fill.classList.add('danger');
                scoreDisplay.classList.add('text-red-500');
                statusEl.innerText = "SYSTEMIC THREAT";
                statusEl.className = "text-red-500 font-bold";
            } else if (hypoVmri >= 150) {
                fill.classList.add('warning');
                scoreDisplay.classList.add('text-yellow-500');
                statusEl.innerText = "ELEVATED RISK";
                statusEl.className = "text-yellow-500 font-bold";
            } else {
                scoreDisplay.classList.add('text-green-500');
                statusEl.innerText = "LOW RISK";
                statusEl.className = "text-green-500 font-bold";
            }

            // 4. Draw Advanced Visuals
            drawBellCurve(hypoVmri);
            generateDeltaAnalysis(data.hypothetical);

            // 5. Default State check
            if (payload.dxy_shift === 0 && payload.tnx_shift === 0 && payload.oas_shift === 0 && payload.vix_shift_pct === 0) {
                statusEl.innerText = "LIVE ENVIRONMENT";
                statusEl.className = "text-zinc-500";
            }
        }
    } catch (e) {
        statusEl.innerText = "API ERROR";
        statusEl.className = "text-red-500 font-bold";
    }
}

// Injects extreme historical variables into the sliders
function applyWarRoomPreset(scenario) {
    const scenarios = {
        '1970s STAG': { dxy: -15, tnx: +3.0, oas: +4.0, vix: +40 },
        '2008 CRASH': { dxy: +12, tnx: -1.5, oas: +15.0, vix: +250 },
        '2020 COVID': { dxy: +8, tnx: -2.5, oas: +8.0, vix: +300 }
    };

    const target = scenarios[scenario];
    if (target) {
        document.getElementById('shiftDxy').value = target.dxy;
        document.getElementById('shiftTnx').value = target.tnx;
        document.getElementById('shiftOas').value = target.oas;
        document.getElementById('shiftVix').value = target.vix;
        
        updateSliderLabels();
        updateWarRoom();
        log(`WAR ROOM: Injected [${scenario}] Scenario Profile`, 'cmd');
    }
}

function resetWarRoom() {
    document.getElementById('shiftDxy').value = 0;
    document.getElementById('shiftTnx').value = 0;
    document.getElementById('shiftOas').value = 0;
    document.getElementById('shiftVix').value = 0;
    
    updateSliderLabels();
    updateWarRoom();
    log('WAR ROOM: Reset to Live Macro Environment', 'info');
}

// --- INITIALIZATION (HOOKING IT ALL UP) ---
document.addEventListener('DOMContentLoaded', () => {
    // 1. Attach listeners to all 4 sliders
    ['shiftDxy', 'shiftTnx', 'shiftOas', 'shiftVix'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', () => {
                updateSliderLabels();
                clearTimeout(warRoomDebounceTimer);
                warRoomDebounceTimer = setTimeout(updateWarRoom, 100); 
            });
        }
    });

    // 2. Attach listeners to the Preset buttons
    const presets = document.querySelectorAll('.btn-preset');
    if (presets.length >= 3) {
        presets[0].addEventListener('click', () => applyWarRoomPreset('1970s STAG'));
        presets[1].addEventListener('click', () => applyWarRoomPreset('2008 CRASH'));
        presets[2].addEventListener('click', () => applyWarRoomPreset('2020 COVID'));
    }

    // 3. Attach listener to Reset button
    const btnReset = document.getElementById('btnResetWarRoom');
    if (btnReset) btnReset.addEventListener('click', resetWarRoom);

    // 4. Run the engine once on load to populate Base Values and visual curve
    if (document.getElementById('shiftDxy')) {
        updateWarRoom();
    }
});

// --- INITIALIZATION (HOOKING IT ALL UP) ---
document.addEventListener('DOMContentLoaded', () => {
    // 1. Attach listeners to all 4 sliders
    ['shiftDxy', 'shiftTnx', 'shiftOas', 'shiftVix'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', () => {
                updateSliderLabels();
                
                // DEBOUNCE: Wait 150ms after they stop dragging before hitting the API
                clearTimeout(warRoomDebounceTimer);
                warRoomDebounceTimer = setTimeout(updateWarRoom, 150); 
            });
        }
    });

    // 2. Attach listeners to the Preset buttons
    const presets = document.querySelectorAll('.btn-preset');
    if (presets.length >= 3) {
        presets[0].addEventListener('click', () => applyWarRoomPreset('1970s STAG'));
        presets[1].addEventListener('click', () => applyWarRoomPreset('2008 CRASH'));
        presets[2].addEventListener('click', () => applyWarRoomPreset('2020 COVID'));
    }

    // 3. Attach listener to Reset button
    const btnReset = document.getElementById('btnResetWarRoom');
    if (btnReset) btnReset.addEventListener('click', resetWarRoom);

    // 4. Run the engine once on load to show current live data
    if (document.getElementById('shiftDxy')) {
        updateWarRoom();
    }
});

// Initialize UI
setInterval(checkStatus, 30000); 
checkStatus();
setInterval(() => document.getElementById('clock').innerText = new Date().toLocaleTimeString(), 1000);

function refreshFrame(id) { 
    document.getElementById(id).src += ''; 
    log(`Refreshed ${id}`, 'cmd'); 
}

async function triggerAction(endpoint) {
    log(`System Command: ${endpoint}`, 'cmd');
    try { 
        const res = await fetch(`${API_BASE}${endpoint}`); 
        const t = await res.text(); 
        log(t, 'success'); 
        refreshFrame('vmriFrame'); 
        refreshFrame('comexFrame');
    } catch (e) { log(e.message, 'error'); }
}

// --- UPGRADED DYNAMIC RESIZER ENGINE (PROMPT 1) ---
document.addEventListener('DOMContentLoaded', () => {
    const resizer = document.getElementById('v-resizer');
    const topPanel = document.getElementById('panelContainer');
    const consoleSection = document.getElementById('consoleSection');

    // Set initial state from memory
    updateLayoutHeights(savedTopHeight);

    // ADD THIS: Restore individual panel zoom levels from memory
    document.querySelectorAll('.draggable-panel').forEach(panel => {
        let savedZoom = localStorage.getItem(`vladhq_zoom_${panel.id}`);
        if (savedZoom) applyZoom(panel.id, parseFloat(savedZoom));
    });
    
    // Create the Event Shield dynamically
    let isResizing = false;
    let shield = document.getElementById('resize-shield') || document.createElement('div');
    if (!shield.id) {
        shield.id = 'resize-shield';
        document.body.appendChild(shield);
    }

    resizer.addEventListener('mousedown', (e) => {
        if (isConsoleMinimized) return; // Disable resizing when hidden
        isResizing = true;
        document.body.classList.add('resizing-active');
        shield.style.display = 'block';
    });

window.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        
        const offsetTop = 48;
        const newHeight = e.clientY - offsetTop;

        // Constraint: Don't crush the console (min 100px) or the charts (min 200px)
        if (newHeight > 200 && newHeight < (window.innerHeight - 150)) {
            updateLayoutHeights(newHeight);
        }
    });

    window.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        document.body.classList.remove('resizing-active');
        shield.style.display = 'none';
    });
});

// ==========================================
// --- 6. SYNCHRONIZED LAYOUT ENGINE ---
// ==========================================

let isConsoleMinimized = false;
let savedTopHeight = localStorage.getItem('vladhq_panel_height') || "550"; // Persistent memory

function updateLayoutHeights(newTopHeight) {
    const topPanel = document.getElementById('panelContainer');
    const consoleSection = document.getElementById('consoleSection');
    const headerHeight = 48;
    const resizerHeight = 4;
    
    // Apply the height to the top
    topPanel.style.height = `${newTopHeight}px`;
    topPanel.style.flex = "none"; // Top panel is the "anchor"

    // The console is flex-1, so it automatically takes (Total - Top - Header)
    // We don't even need to set the console height manually!
    
    // Save for persistence
    if (!isConsoleMinimized) {
        savedTopHeight = newTopHeight;
        localStorage.setItem('vladhq_panel_height', savedTopHeight);
    }

    // Refresh visual components
    if (typeof drawBellCurve === 'function') {
        drawBellCurve(parseFloat(document.getElementById('warVmriScore').innerText || 0));
    }
}

function toggleConsole() {
    const consoleSection = document.getElementById('consoleSection');
    const consoleBody = document.getElementById('consoleBody');
    const resizer = document.getElementById('v-resizer');
    const minBtn = document.getElementById('btnMinConsole');
    const topPanel = document.getElementById('panelContainer');

    if (!isConsoleMinimized) {
        // MINIMIZE LOGIC
        isConsoleMinimized = true;
        consoleBody.classList.add('hidden');
        resizer.classList.add('hidden');
        
        // Push top panel to maximum possible height
        const availableHeight = window.innerHeight - 48 - 45; // Minus header and console tab
        topPanel.style.height = `${availableHeight}px`;
        
        minBtn.innerText = "[Expand]";
        log("Console Stashed: Maximum Workspace Active", "info");
    } else {
        // EXPAND LOGIC (Restore from Memory)
        isConsoleMinimized = false;
        consoleBody.classList.remove('hidden');
        resizer.classList.remove('hidden');
        
        // Snap back to exactly where the user last had it
        updateLayoutHeights(savedTopHeight);
        
        minBtn.innerText = "[Minimize]";
        log("Console Restored to User Position", "info");
    }
}

// Fetches the live XML dump and extracts the Paper:Physical ratio
async function syncComexModule() {
    try {
        const res = await fetch(`${API_BASE}/api/dump`);
        const xmlText = await res.text();
        
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        
        // Find the node in the XML
        const ratioNode = xmlDoc.querySelector("comex_default_risk leverage_ratio");
        
        if (ratioNode) {
            // The XML outputs "7.17:1", so we split by ':' to grab just the number
            const ratioStr = ratioNode.textContent.split(':')[0]; 
            const ratio = parseFloat(ratioStr);
            
            // Push the live data to the UI
            updateComexRatioUI(ratio);
        }
    } catch (e) { 
        console.error("Failed to sync COMEX module:", e); 
    }
}

// Updates the COMEX Paper:Physical Module UI based on the current ratio
function updateComexRatioUI(ratio) {
    const display = document.getElementById('livePaperRatio');
    const banner = document.getElementById('liveRatioStatusBanner');
    const claims = document.getElementById('livePaperOz');
    const statusIcon = document.getElementById('ratioStatusIcon');
    const statusText = document.getElementById('ratioStatusText');
    const needle = document.getElementById('ratioNeedle'); // Grab the needle

    if (!display) return;

    // 1. Update text numbers
    display.innerText = `${ratio.toFixed(0)}:1`;
    claims.innerText = ratio.toFixed(0);

    // 2. Animate the Gauge Needle
    // Math: Maps a 0 to 50 ratio scale to a -90 to +90 degree angle.
    let degrees = -90 + (ratio / 50) * 180;
    if (degrees > 90) degrees = 90;   // Cap it at far right
    if (degrees < -90) degrees = -90; // Cap it at far left
    
    if (needle) {
        needle.style.transform = `rotate(${degrees}deg)`;
    }

    // 3. Dynamic Threat Tiering Colors
    if (ratio >= 40) {
        display.className = "text-4xl font-bold tracking-tighter text-red-500 drop-shadow-[0_0_12px_rgba(239,68,68,0.4)]";
        banner.className = "text-[9px] uppercase font-bold text-red-500 mt-1 tracking-widest";
        banner.innerText = "CRITICAL LEVERAGE";
        statusIcon.className = "text-red-500 mt-[1px]";
        statusText.innerHTML = "<span class='text-red-400 font-bold'>Critical ratio level</span>";
    } else if (ratio >= 25) {
        display.className = "text-4xl font-bold tracking-tighter text-yellow-500 drop-shadow-[0_0_12px_rgba(234,179,8,0.3)]";
        banner.className = "text-[9px] uppercase font-bold text-yellow-500 mt-1 tracking-widest";
        banner.innerText = "DELIVERY STRESS";
        statusIcon.className = "text-yellow-500 mt-[1px]";
        statusText.innerHTML = "<span class='text-yellow-400 font-bold'>Elevated ratio level</span>";
    } else {
        display.className = "text-4xl font-bold tracking-tighter text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.2)]";
        banner.className = "text-[9px] uppercase font-bold text-green-500 mt-1 tracking-widest";
        banner.innerText = "MARKET NOMINAL";
        statusIcon.className = "text-green-500 mt-[1px]";
        statusText.innerHTML = "<span class='text-green-400'>Standard leverage level</span>";
    }
}


// Unified Initialization
document.addEventListener('DOMContentLoaded', () => {
    const resizer = document.getElementById('v-resizer');
    const topPanel = document.getElementById('panelContainer');

    // Fetch the live ratio immediately on load
    syncComexModule();
    
    // Keep it updated every 5 minutes (300,000 ms) in the background
    setInterval(syncComexModule, 300000);
    
    // Set initial layout from memory
    updateLayoutHeights(savedTopHeight);

    // Event Shield Logic
    let isResizing = false;
    let shield = document.getElementById('resize-shield') || document.createElement('div');
    if (!shield.id) {
        shield.id = 'resize-shield';
        document.body.appendChild(shield);
    }

    resizer.addEventListener('mousedown', (e) => {
        if (isConsoleMinimized) return;
        isResizing = true;
        document.body.classList.add('resizing-active');
        shield.style.display = 'block';
    });

    window.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        
        const offsetTop = 48; // Header height
        const newHeight = e.clientY - offsetTop;

        // Constraints: Min 200px top, leave at least 150px for console
        if (newHeight > 200 && newHeight < (window.innerHeight - 150)) {
            updateLayoutHeights(newHeight);
        }
    });

    window.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        document.body.classList.remove('resizing-active');
        shield.style.display = 'none';
    });
});

// Initialize UI Clocks/Status
setInterval(checkStatus, 30000); 
checkStatus();
setInterval(() => {
    const clock = document.getElementById('clock');
    if(clock) clock.innerText = new Date().toLocaleTimeString();
}, 1000);

// ==========================================
// --- DEALER POSITIONING (GEX) ENGINE ---
// ==========================================

let gexChartInstance = null;

async function loadDealerMap() {
    const ticker = document.getElementById('gexTickerInput').value.toUpperCase() || 'SPY';
    document.getElementById('gexTickerInput').value = ticker;
    
    log(`Scanning Dealer Options chain for ${ticker}...`, 'cmd');

    try {
        // --- REAL DATA PIPELINE ---
        const res = await fetch(`${API_BASE}/api/gex?ticker=${ticker}`);
        const json = await res.json();
        
        if (json.status !== 'success') {
            log(`GEX Error: ${json.message}`, 'error');
            return;
        }
        
        const data = json.data;
        
        // --- UPDATE UI STATS ---
        document.getElementById('gexSpot').innerText = `$${data.spot.toFixed(2)}`;
        document.getElementById('gexZero').innerText = `$${data.zeroGamma.toFixed(2)}`;
        document.getElementById('gexCallWall').innerText = `$${data.callWall.toFixed(2)}`;
        document.getElementById('gexPutWall').innerText = `$${data.putWall.toFixed(2)}`;

        // --- RENDER CHART ---
        const ctx = document.getElementById('gexChart').getContext('2d');
        
        // Destroy existing chart if user scans a new ticker
        if (gexChartInstance) {
            gexChartInstance.destroy();
        }

        // Separate data into positive (calls) and negative (puts) for coloring
        const backgroundColors = data.gamma.map(val => 
            val >= 0 ? 'rgba(34, 197, 94, 0.8)' : 'rgba(239, 68, 68, 0.8)'
        );
        const borderColors = data.gamma.map(val => 
            val >= 0 ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'
        );

        gexChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.strikes,
                datasets: [{
                    label: 'Net Dealer Gamma',
                    data: data.gamma,
                    backgroundColor: backgroundColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false, // CRITICAL for zoom/maximize panel scaling
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                let val = context.raw;
                                return `Net Gamma: ${formatCompact(val.toString())}`;
                            }
                        }
                    },
                    // Draw a vertical line for Spot Price
                    annotation: {
                        annotations: {
                            line1: {
                                type: 'line',
                                xMin: data.strikes.indexOf(data.spot),
                                xMax: data.strikes.indexOf(data.spot),
                                borderColor: 'white',
                                borderWidth: 2,
                                borderDash: [5, 5],
                                label: { content: 'SPOT', display: true, position: 'top', color: 'white', backgroundColor: '#000' }
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.1)' },
                        ticks: { color: '#a1a1aa', font: { size: 9 }, callback: (v) => formatCompact(v.toString()) }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#a1a1aa', font: { size: 9 }, maxTicksLimit: 15 }
                    }
                }
            },
            plugins: [{
                // Custom plugin to draw the Spot Line without needing extra Chart.js annotation libraries
                id: 'spotLinePlugin',
                afterDraw: (chart) => {
                    const xAxis = chart.scales.x;
                    const yAxis = chart.scales.y;
                    const ctx = chart.ctx;
                    
                    // Find closest strike to spot
                    let closestIdx = 0;
                    let minDiff = Infinity;
                    data.strikes.forEach((strike, i) => {
                        let diff = Math.abs(strike - data.spot);
                        if (diff < minDiff) { minDiff = diff; closestIdx = i; }
                    });

                    const xPixel = xAxis.getPixelForValue(closestIdx);
                    
                    ctx.save();
                    ctx.beginPath();
                    ctx.setLineDash([5, 5]);
                    ctx.moveTo(xPixel, yAxis.top);
                    ctx.lineTo(xPixel, yAxis.bottom);
                    ctx.lineWidth = 1.5;
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
                    ctx.stroke();
                    
                    ctx.fillStyle = '#fff';
                    ctx.font = 'bold 9px JetBrains Mono';
                    ctx.fillText('SPOT', xPixel + 4, yAxis.top + 10);
                    ctx.restore();
                }
            }]
        });

        log(`GEX Profile loaded successfully.`, 'success');
        
    } catch (e) {
        log(`Failed to load GEX map: ${e.message}`, 'error');
    }
}