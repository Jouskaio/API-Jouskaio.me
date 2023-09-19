import express from 'express'
import email from './routes/email.mjs'

const app = express()

app.use('/api', email);


app.listen(2000, () => {
  console.log("Server listening on http://localhost:2000")  ;
})