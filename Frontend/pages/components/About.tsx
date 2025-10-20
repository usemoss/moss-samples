import React from "react";
import config from "../index.json";
import Image from "next/image";

const About = () => {
  const about = config.about;
  return (
    <div id="About" className="px-8 md:px-32 py-20 content-center bg-gray-50 dark:bg-zinc-950 transition-colors duration-300">
      <h1 className="pt-12 uppercase font-bold text-center text-gray-900 dark:text-white text-4xl mb-16">
        {about.title}
      </h1>
      <div className="flex flex-col md:flex-row align-center items-center max-w-6xl mx-auto">
        <div className="w-full md:w-1/2 flex justify-center content-center mb-8 md:mb-0">
          <Image 
            src={about.image} 
            alt="about" 
            className="shadow-2xl rounded-2xl border-4 border-fuchsia-500 dark:border-fuchsia-400" 
            width={300} 
            height={300}
          />
        </div>
        <div className="w-full md:w-1/2 md:ml-8 text-center md:text-left">
          <div className="about__primary text-gray-800 dark:text-gray-200 text-lg leading-relaxed">
            <span>{about.primary}</span>
          </div>
          <div className="mt-6 text-gray-700 dark:text-gray-300 leading-relaxed">
            <span>{about.secondary}</span>
          </div>
          <div className="mt-8 inline-block">
            <a 
              href={'#'} 
              className="inline-block px-6 py-3 text-center font-bold text-white bg-gradient-to-r from-pink-600 via-fuchsia-600 to-purple-600 rounded-lg hover:shadow-lg hover:scale-105 transition-all duration-200"
            >
              View Website
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default About;