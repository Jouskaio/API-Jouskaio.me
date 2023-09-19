import express, { query } from 'express'

const email = express.Router();


email.post('/newMessage', async (req, res) => {
    try {
        console.log(req.query);

    } catch (error) {
        console.error(error);
        res.status(500).send("Error server");
    }
    res.end
});

export default email;