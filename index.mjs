import express from 'express'
import emailRouter from './routes/email.mjs'
import dotenv from 'dotenv';
// Configure dotenv to read .env file
dotenv.config();
const app = express()
// Middleware to analyse JSON data in request body
app.use(express.json());

// Routes
app.use('/v1/email', emailRouter);


app.listen(2000, () => {
  console.log("Server listening on http://localhost:2000")  ;
})