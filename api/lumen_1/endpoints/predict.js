const express = require('express');
const predictRouter = express.Router();
const axios = require('axios');

const PREDICTION_SERVICE_URL = 'https://lumen-back-end-flask.onrender.com/predict';

// Middleware for /predict
predictRouter.use((req, res, next) => {
    next();
});

// Endpoint to handle prediction requests
predictRouter.post('/', async (req, res, next) => {
    try {
        const { input_data } = req.body;
        if (!input_data) {
            return res.status(400).json({ success: false, message: 'Input data is required' });
        }

        // Make a request to Lumen for prediction
        const response = await axios.post(PREDICTION_SERVICE_URL, { input_data });
        const prediction = response.data;

        res.json({ success: true, prediction });
    } catch (error) {
        next(error);
    }
});

module.exports = predictRouter;