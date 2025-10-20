import React from "react";
import config from "../index.json";

const Footer = () => {
  const footer = config.footer;
  const getYear = () => {
    return new Date().getFullYear();
  };

  return (
    <div className="footer px-8 py-16 flex justify-center align-center flex-col bg-neutral-800">
      <div className="mx-auto text-3xl text-neutral-400 mb-8 space-x-10">
        <a rel="noreferrer" href={footer.twitter} target="_blank">
          <i className="devicon-twitter-original"></i>
        </a>
        <a rel="noreferrer" href={footer.linkedin} target="_blank">
          <i className="devicon-linkedin-plain"></i>
        </a>
        <a rel="noreferrer" href={footer.github} target="_blank">
          <i className="devicon-github-original"></i>
        </a>
      </div>
      <span className="text-sm text-center text-neutral-600">
        © {getYear()} - Template developed by <a href="https://www.dylanarveson.com">Dylan Arveson</a>
      </span>
    </div>
  );
};

export default Footer;