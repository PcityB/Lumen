const WebSocket = require('ws');
require('dotenv').config();
const moment = require('moment-timezone');
const { createRealTimeSPXRecord } = require('../../db/helperFunctions/realTimeSPX');
const { createRealTimeSPYRecord } = require('../../db/helperFunctions/realTimeSPY');
const { createRealTimeVIXRecord } = require('../../db/helperFunctions/realTimeVIX'); 
const Bottleneck = require('bottleneck');

const API_KEY = process.env.FINNHUB_API_KEY;
const SOCKET_URL = `wss://ws.finnhub.io?token=${API_KEY}`;

const limiter = new Bottleneck({
    minTime: 1000, // 1 second between requests
    maxConcurrent: 1
});

let socket;

const handleWebSocket = () => {
    socket = new WebSocket(SOCKET_URL);

    socket.on('open', () => {
        console.log('WebSocket connection opened');
        socket.send(JSON.stringify({ 'type': 'subscribe', 'symbol': '^GSPC' })); 
        socket.send(JSON.stringify({ 'type': 'subscribe', 'symbol': 'SPY' })); 
        socket.send(JSON.stringify({ 'type': 'subscribe', 'symbol': '^VIX' })); 
        console.log('Subscribed to ^GSPC, SPY, and ^VIX trade data.');
    });

    socket.on('message', async (data) => {
        const message = data.toString();
        const parsedData = JSON.parse(message);
        console.log('Received data:', parsedData);

        if (parsedData.type === 'trade') {
            parsedData.data.forEach(async (trade) => {
                const utcTimestamp = new Date(trade.t);
                const centralTime = moment(utcTimestamp).tz('America/Chicago').format(); 
                const current_price = trade.p;
                const volume = trade.v;
                const conditions = trade.c ? trade.c.join(', ') : null; 
                const symbol = trade.s;
                console.log(`Symbol: ${symbol}, Timestamp (Central): ${centralTime}, Price: ${current_price}`);

                try {
                    await limiter.schedule(async () => {
                        if (symbol === 'SPY') {
                            await createRealTimeSPYRecord({ timestamp: centralTime, current_price, volume, conditions });
                        } else if (symbol === 'GSPC' || symbol === '^GSPC' || symbol === 'OANDA:SPX500_USD') {
                            await createRealTimeSPXRecord({ timestamp: centralTime, current_price, volume, conditions });
                        } else if (symbol === '^VIX') {
                            await createRealTimeVIXRecord({ timestamp: centralTime, current_price, volume, conditions });
                        }
                        console.log('Data point stored successfully');
                    });
                } catch (error) {
                    console.error('Error storing real-time data:', error);
                }
            });
        } else if (parsedData.type === 'ping') {
            console.log('Received ping message');
        } else {
            console.log('Received unknown message type:', parsedData.type);
        }
    });

    socket.on('close', () => {
        console.log('WebSocket connection closed');
    });

    socket.on('error', (error) => {
        console.error(`WebSocket error: ${error}`);
    });
};

const restartWebSocket = () => {
    if (socket) {
        socket.terminate();
    }
    handleWebSocket();
};

module.exports = { handleWebSocket, restartWebSocket };