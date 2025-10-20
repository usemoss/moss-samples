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
      return <p>Thanks for joining!</p>;
  }

  return (
    <div className="w-full sm:w-full md:w-3/4 lg:w-1/2 mt-16 mx-auto">
      <form 
        onSubmit={handleSubmit} 
        action={`https://formspree.io/f/${contact.formId}`}
        method="post" 
        className="bg-white shadow-md rounded px-8 pt-6 pb-8 mb-4"
      >
        <div className="mb-4">
          <label className="block text-gray-700 font-bold mb-2" htmlFor="name">
            Name
          </label>
          <input
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline"
            id="name"
            type="text"
            name="name"
            placeholder="Enter your name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="mb-4">
          <label className="block text-gray-700 font-bold mb-2" htmlFor="email">
            Email
          </label>
          <input
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline"
            id="email"
            type="email"
            name="email"
            placeholder="Enter your email address"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="mb-4">
          <label className="block text-gray-700 font-bold mb-2" htmlFor="message">
            Message
          </label>
          <textarea
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline"
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
            className="text-lg font-bold p-0.5 mt-6 w-44 bg-gradient-to-r from-rose-400 via-fuchsia-500 to-indigo-500"
          >
            <div className="bg-white">
              <span className="block p-2 font-semibold bg-white font-bold bg-gradient-to-r from-rose-400 via-fuchsia-500 to-indigo-500 bg-clip-text text-transparent">
                Send
              </span>
          </div>
        </button>
        </div>
      </form>
    </div>
  );
}

export default ContactForm;
