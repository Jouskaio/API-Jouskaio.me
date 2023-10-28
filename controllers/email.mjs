import nodemailer from "nodemailer";

export default async function postEmail(req, res) {
  try {
    const { email, title, message, name } = req.query;
    console.log('email', process.env.NODEMAILER_USER);
    const mailOptions = {
      from: email,
      to: process.env.NODEMAILER_USER,
      subject: name + " : " + title,
      text: message,
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

    await transporter.sendMail(mailOptions, (error, info) => {
      if (error) {
        console.log(error);
        return res.status(500).json({error: 'Error while sending an email from ' + email + ' to ' + process.env.NODEMAILER_USER + ' with title ' + title + ' : ' + error});
      } else {
        return res.json({message: 'Email send with success'});
      }
    });
  } catch (error) {
    console.error(error);
    return res.status(500).send('Internal Server Error');
  }
}
