import express from 'express'
import emailRouter from './routes/email.mjs'
import dotenv from 'dotenv';
import cors from 'cors';
// Configure dotenv to read .env file
dotenv.config();
const app = express()

// Middleware to analyse JSON data in request body
app.use(express.json());

// Routes
app.use('/v1/email', emailRouter);


const port = process.env.PORT || 2000; // Utilisez le port spécifié par l'environnement ou le port 2000 par défaut
app.listen(port, () => {
  console.log(`Server listening on port ${port}`);
});