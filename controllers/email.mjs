import nodemailer from "nodemailer";
import nodemailerNewMail from "../frameworks/services/nodemailer/newMail.mjs";

export default async function postEmail(req, res) {
  try {
    const { email, title, message, name } = req.body;
    const mailOptions = {
      from: email,
      to: process.env.NODEMAILER_USER,
      subject: title,
      html: nodemailerNewMail(title, message, name)
    };

    const transporter = nodemailer.createTransport({
      host: "smtp.ionos.fr",
      port: 587,
      secure: false,
      auth: {
        user: process.env.NODEMAILER_USER,
        pass: process.env.NODEMAILER_PASS
      }
    });

    if (!email || !title || !message || !name) {
      return res.status(400).json({error: 'Missing parameters'});
    } else {
      await transporter.sendMail(mailOptions, (error, info) => {
        if (error) {
          return res.status(500).json({error: 'Error while sending an email from ' + email + ' to ' + process.env.NODEMAILER_USER + ' with title ' + title + ' : ' + error});
        } else {
          return res.json({message: 'Email send with success'});
        }
      });
    }
  } catch (error) {
    return res.status(500).send('Internal Server Error');
  }
}
