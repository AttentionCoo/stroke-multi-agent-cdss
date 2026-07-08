package com.it.po.uo;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
//@TableName("user")
public class LoginInfo {
    private String name;
    private String image;
    //@TableField(exist = false)
    private String token;
}
