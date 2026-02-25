package com.webapp;

import org.junit.Test;
import static org.junit.Assert.*;

public class HelloServletTest {

    @Test
    public void testServletInstantiation() {
        HelloServlet servlet = new HelloServlet();
        assertNotNull(servlet);
    }
}
