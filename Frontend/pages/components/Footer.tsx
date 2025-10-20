import React from "react";
import config from "../index.json";

const Footer = () => {
  const footer = config.footer;
  const getYear = () => {
    return new Date().getFullYear();
  };

  return (
    <div className="footer px-8 py-16 flex justify-center align-center flex-col bg-white dark:bg-zinc-950 border-t border-gray-200 dark:border-zinc-800 transition-colors duration-300">
      <div className="mx-auto text-3xl text-gray-600 dark:text-gray-400 mb-8 space-x-10">
        <a rel="noreferrer" href={footer.twitter} target="_blank" className="hover:text-fuchsia-600 dark:hover:text-fuchsia-400 transition-colors duration-200">
          <i className="devicon-twitter-original"></i>
        </a>
        <a rel="noreferrer" href={footer.linkedin} target="_blank" className="hover:text-fuchsia-600 dark:hover:text-fuchsia-400 transition-colors duration-200">
          <i className="devicon-linkedin-plain"></i>
        </a>
        <a rel="noreferrer" href={footer.github} target="_blank" className="hover:text-fuchsia-600 dark:hover:text-fuchsia-400 transition-colors duration-200">
          <i className="devicon-github-original"></i>
        </a>
      </div>
      <span className="text-sm text-center text-gray-600 dark:text-gray-500">
      </span>
    </div>
  );
};

export default Footer;