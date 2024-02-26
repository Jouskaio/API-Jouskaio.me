import nodemailer from "nodemailer";
import nodemailerNewMail from "../frameworks/services/nodemailer/newMail.mjs";
import path from 'path';

export default async function postEmail(req, res) {
  try {
    const { email, title, message, name } = req.body;
    const mailOptions = {
      from: email,
      to: process.env.NODEMAILER_USER,
      subject: title,
      html: nodemailerNewMail(title, message, name),
      attachments: [
        {
          filename: 'x.png',
          path: path.resolve(import.meta.url, '../icons/x.png'),
          cid: 'twitter'
        },
        {
          filename: 'insta.png',
          path: path.resolve(import.meta.url, '../icons/insta.png'),
          cid: 'insta'
        },
        {
          filename: 'linkedin.png',
          path: path.resolve(import.meta.url, '../icons/linkedin.png'),

          cid: 'linkedin'
        },
        {
          filename: 'spotify.png',
          path: path.resolve(import.meta.url, '../icons/spotify.png'),
          cid: 'spotify'
        },
      ]
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
          console.error('An error occurred:', error.stack);
          return res.status(500).json({error: 'Error while sending an email from ' + email + ' to ' + process.env.NODEMAILER_USER + ' with title ' + title + ' : ' + error});
        } else {
          return res.json({message: 'Email send with success'});
        }
      });
    }
  } catch (error) {
    console.error('An error occurred:', error.stack);
    return res.status(500).send('Internal Server Error');
  }
}
