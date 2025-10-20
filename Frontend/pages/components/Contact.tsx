import React from "react";
import config from "../index.json";
import ContactForm from "./ContactForm";

const Contact = () => {
  const contact = config.contact;
  return (
    <div id={contact.title} className="px-8 sm:px-12 md:px-32 py-20 flex justify-center align-center flex-col bg-gray-50 dark:bg-zinc-950 transition-colors duration-300">
      <h2 className="mt-12 uppercase font-bold text-center text-gray-900 dark:text-white text-4xl mb-8">{contact.title}</h2>
      <ContactForm />
    </div>
  );
};

export default Contact;