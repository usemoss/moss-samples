import React, { useState } from "react";
import { useForm, ValidationError } from '@formspree/react';
import config from "../index.json";

function ContactForm() {
  const contact = config.contact;
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");

  const [state, handleSubmit] = useForm(contact.formId);
  if (state.succeeded) {
      return (
        <p className="text-center text-lg text-gray-900 dark:text-white mt-8">
          Thanks for joining!
        </p>
      );
  }

  return (
    <div className="w-full sm:w-full md:w-3/4 lg:w-1/2 mt-16 mx-auto">
      <form 
        onSubmit={handleSubmit} 
        action={`https://formspree.io/f/${contact.formId}`}
        method="post" 
        className="bg-white dark:bg-zinc-900 shadow-xl rounded-2xl px-8 pt-6 pb-8 mb-4 border border-gray-200 dark:border-zinc-800 transition-colors duration-300"
      >
        <div className="mb-6">
          <label className="block text-gray-700 dark:text-gray-300 font-bold mb-2" htmlFor="name">
            Name
          </label>
          <input
            className="shadow appearance-none border border-gray-300 dark:border-zinc-700 rounded-lg w-full py-3 px-4 text-gray-700 dark:text-gray-200 bg-white dark:bg-zinc-800 leading-tight focus:outline-none focus:ring-2 focus:ring-fuchsia-500 focus:border-transparent transition-colors duration-200"
            id="name"
            type="text"
            name="name"
            placeholder="Enter your name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="mb-6">
          <label className="block text-gray-700 dark:text-gray-300 font-bold mb-2" htmlFor="email">
            Email
          </label>
          <input
            className="shadow appearance-none border border-gray-300 dark:border-zinc-700 rounded-lg w-full py-3 px-4 text-gray-700 dark:text-gray-200 bg-white dark:bg-zinc-800 leading-tight focus:outline-none focus:ring-2 focus:ring-fuchsia-500 focus:border-transparent transition-colors duration-200"
            id="email"
            type="email"
            name="email"
            placeholder="Enter your email address"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="mb-6">
          <label className="block text-gray-700 dark:text-gray-300 font-bold mb-2" htmlFor="message">
            Message
          </label>
          <textarea
            className="shadow appearance-none border border-gray-300 dark:border-zinc-700 rounded-lg w-full py-3 px-4 text-gray-700 dark:text-gray-200 bg-white dark:bg-zinc-800 leading-tight focus:outline-none focus:ring-2 focus:ring-fuchsia-500 focus:border-transparent transition-colors duration-200"
            id="message"
            name="message"
            rows={5}
            placeholder="Enter your message"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
          />
          <ValidationError 
            prefix="Message" 
            field="message"
            errors={state.errors}
          />
        </div>
        <div className="flex items-center justify-center">
          <button 
            type="submit"
            disabled={state.submitting}
            className="px-8 py-3 text-lg font-bold text-white bg-gradient-to-r from-pink-600 via-fuchsia-600 to-purple-600 rounded-lg hover:shadow-lg hover:scale-105 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

export default ContactForm;
