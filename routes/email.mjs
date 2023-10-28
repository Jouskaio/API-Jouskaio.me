import express from "express";
import postEmail from "../controllers/email.mjs";
const router = express.Router()

router.post('/', postEmail)


export default router;