package com.webapp;

import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.annotation.WebServlet;
import java.io.IOException;
import java.io.PrintWriter;

@WebServlet("/hello")
public class HelloServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.setContentType("text/html;charset=UTF-8");
        PrintWriter out = response.getWriter();
        out.println("<!DOCTYPE html>");
        out.println("<html><head><title>Hello</title></head>");
        out.println("<body>");
        out.println("<h1>Hello from webapp-210401210447!</h1>");
        out.println("<p>Java version: " + System.getProperty("java.version") + "</p>");
        out.println("<p>Server time: " + new java.util.Date() + "</p>");
        out.println("</body></html>");
    }
}
